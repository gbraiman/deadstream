"""DataUpdateCoordinator for Deadstream."""
from __future__ import annotations

import logging
from datetime import date as _date, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .archive_client import ArchiveClient, Show, Track
from .const import (
    DEFAULT_COLLECTIONS,
    DEFAULT_FAVORED_TAPER,
    DEFAULT_PLAY_LOSSLESS,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .utils import normalize_collections

_LOGGER = logging.getLogger(__name__)


class DeadstreamCoordinator(DataUpdateCoordinator):
    """Manages state and data fetching for Deadstream."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        collections: list[str] | None = None,
        play_lossless: bool = DEFAULT_PLAY_LOSSLESS,
        favored_taper: str = DEFAULT_FAVORED_TAPER,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.client = ArchiveClient(session)
        self.collections = normalize_collections(collections)
        self.play_lossless = play_lossless
        self.favored_taper = favored_taper

        # Date browsing — month + day only; results span all years
        _today = _date.today()
        self.selected_month: int = _today.month
        self.selected_day: int = _today.day

        # Level 1: one unique show per year for the selected month/day
        self.available_shows: list[Show] = []
        self.current_show_index: int = 0

        # Level 2: all recordings (tapers) for the currently selected year/date
        self.available_tapers: list[Show] = []
        self.current_taper_index: int = 0
        self._tapers_for_show_identifier: str | None = None

        # Playback
        self.current_tracks: list[Track] = []
        self.current_track_index: int = 0
        self.is_playing: bool = False

        # Target player(s)
        self.target_players: list[str] = []
        self.default_player: str = ""

    # ------------------------------------------------------------------
    # Compat shim so old code that reads/writes target_player still works
    # ------------------------------------------------------------------
    @property
    def target_player(self) -> str | None:
        return self.target_players[0] if self.target_players else None

    @target_player.setter
    def target_player(self, value: str | None) -> None:
        self.target_players = [value] if value else []

    # ------------------------------------------------------------------
    # Current show resolution
    # ------------------------------------------------------------------
    @property
    def current_show(self) -> Show | None:
        """Active show: selected taper only when it belongs to selected show."""
        selected_show = (
            self.available_shows[self.current_show_index]
            if self.available_shows and 0 <= self.current_show_index < len(self.available_shows)
            else None
        )
        if (
            selected_show
            and self.available_tapers
            and 0 <= self.current_taper_index < len(self.available_tapers)
            and self._tapers_for_show_identifier == selected_show.identifier
        ):
            return self.available_tapers[self.current_taper_index]
        return selected_show

    @property
    def current_track(self) -> Track | None:
        if self.current_tracks and 0 <= self.current_track_index < len(self.current_tracks):
            return self.current_tracks[self.current_track_index]
        return None

    # ------------------------------------------------------------------
    # Data fetch — always month+day across all years
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> dict[str, Any]:
        try:
            shows = await self.client.search_today_in_history(
                collections=self.collections,
                month=self.selected_month,
                day=self.selected_day,
                favored_taper=self.favored_taper,
            )
            self.available_shows = shows
            if self.current_show_index >= len(self.available_shows):
                self.current_show_index = 0

            # Do not auto-populate tapers on refresh/date changes.
            # Keep an existing taper list only if it still belongs to the
            # currently selected show; otherwise clear stale taper state.
            selected_show = (
                self.available_shows[self.current_show_index]
                if self.available_shows and 0 <= self.current_show_index < len(self.available_shows)
                else None
            )
            selected_identifier = selected_show.identifier if selected_show else None
            if not selected_show or self._tapers_for_show_identifier != selected_identifier:
                self.available_tapers = []
                self.current_taper_index = 0
                self._tapers_for_show_identifier = None
        except Exception as err:
            raise UpdateFailed(f"Error fetching shows: {err}") from err

        return {
            "shows": self.available_shows,
            "month": self.selected_month,
            "day": self.selected_day,
        }

    # ------------------------------------------------------------------
    # Date navigation
    # ------------------------------------------------------------------
    async def async_set_date(self, month: int, day: int) -> None:
        """Set month/day and refresh the cross-year show list."""
        self.selected_month = month
        self.selected_day = day
        self.current_show_index = 0
        self.reset_tapers_and_tracks()
        await self.async_refresh()

    async def async_today_in_history(self) -> None:
        """Jump to today's month/day."""
        today = _date.today()
        await self.async_set_date(today.month, today.day)

    def reset_tapers_and_tracks(self) -> None:
        """Clear taper/track state when band filters or date context change."""
        self.available_tapers = []
        self.current_taper_index = 0
        self._tapers_for_show_identifier = None
        self.current_tracks = []
        self.current_track_index = 0
        self.is_playing = False

    # ------------------------------------------------------------------
    # Show selection (level 1 — choose a year)
    # ------------------------------------------------------------------
    async def async_select_show(self, index: int) -> None:
        """Select a year-level show and load all its taper recordings."""
        self.current_show_index = index
        self.current_tracks = []
        self.current_track_index = 0
        self.is_playing = False

        # Invalidate stale taper list immediately so UI cannot keep showing
        # tapers from a previously selected show if loading fails.
        self.available_tapers = []
        self.current_taper_index = 0
        self._tapers_for_show_identifier = None

        show = self.available_shows[index] if 0 <= index < len(self.available_shows) else None
        if show:
            # Immediate show-scoped fallback so old taper labels cannot linger
            # while the async archive lookup is in flight.
            self.available_tapers = [show]
            self.current_taper_index = 0
            self._tapers_for_show_identifier = show.identifier
            await self._async_load_tapers_for_show(show)

        self.async_update_listeners()

    async def async_load_tapers_for_current_show(self) -> None:
        """Load tapers for the currently selected show."""
        show = self.available_shows[self.current_show_index] if self.available_shows else None
        if not show:
            self.available_tapers = []
            self.current_taper_index = 0
            self._tapers_for_show_identifier = None
            self.async_update_listeners()
            return

        # Clear stale values before reload, then pin to selected show while loading.
        self.available_tapers = [show]
        self.current_taper_index = 0
        self._tapers_for_show_identifier = show.identifier
        await self._async_load_tapers_for_show(show)
        self.async_update_listeners()

    async def _async_load_tapers_for_show(self, show: Show) -> None:
        """Fetch all recordings for show's date, sorted by downloads (best first)."""
        try:
            d = _date.fromisoformat(show.date[:10])
        except (TypeError, ValueError, AttributeError):
            self.available_tapers = []
            self.current_taper_index = 0
            self._tapers_for_show_identifier = None
            return

        try:
            tapers = await self.client.search_tapers_for_date(
                collections=[show.collection],  # scope to this band only
                year=d.year,
                month=d.month,
                day=d.day,
                favored_taper=self.favored_taper,
            )
        except Exception as err:  # defensive: never leave stale prior tapers in place
            _LOGGER.warning("Failed loading tapers for %s (%s): %s", show.identifier, show.collection, err)
            tapers = []

        # If selection changed while this request was in flight, drop stale results.
        selected_show = (
            self.available_shows[self.current_show_index]
            if self.available_shows and 0 <= self.current_show_index < len(self.available_shows)
            else None
        )
        if not selected_show or selected_show.identifier != show.identifier:
            return

        # Keep the selected show as a fallback so the taper selector is never empty
        # when archive.org returns sparse/partial metadata for this date.
        self.available_tapers = tapers or [show]
        self.current_taper_index = 0
        self._tapers_for_show_identifier = show.identifier

    # ------------------------------------------------------------------
    # Taper selection (level 2 — choose a specific recording)
    # ------------------------------------------------------------------
    def select_taper(self, index: int) -> None:
        """Select a specific recording by index. Stops playback."""
        self.current_taper_index = index
        self.current_tracks = []
        self.current_track_index = 0
        if self.is_playing:
            self.is_playing = False
        self.async_update_listeners()

    # ------------------------------------------------------------------
    # Track loading
    # ------------------------------------------------------------------
    async def async_load_show(self, show: Show) -> bool:
        tracks = await self.client.get_show_tracks(show.identifier, self.play_lossless)
        if not tracks:
            _LOGGER.warning("No tracks found for %s", show.identifier)
            return False
        self.current_tracks = tracks
        self.current_track_index = 0
        return True

    async def async_load_current_show(self) -> bool:
        show = self.current_show
        if not show:
            return False
        return await self.async_load_show(show)

    # ------------------------------------------------------------------
    # Show/track navigation
    # ------------------------------------------------------------------
    def next_show(self) -> bool:
        if not self.available_shows:
            return False
        self.current_show_index = (self.current_show_index + 1) % len(self.available_shows)
        self.available_tapers = []
        self.current_taper_index = 0
        self._tapers_for_show_identifier = None
        self.current_tracks = []
        self.current_track_index = 0
        self.is_playing = False
        return True

    def prev_show(self) -> bool:
        if not self.available_shows:
            return False
        self.current_show_index = (self.current_show_index - 1) % len(self.available_shows)
        self.available_tapers = []
        self.current_taper_index = 0
        self._tapers_for_show_identifier = None
        self.current_tracks = []
        self.current_track_index = 0
        self.is_playing = False
        return True

    def next_track(self) -> bool:
        if self.current_tracks and self.current_track_index < len(self.current_tracks) - 1:
            self.current_track_index += 1
            return True
        return False

    def prev_track(self) -> bool:
        if self.current_tracks and self.current_track_index > 0:
            self.current_track_index -= 1
            return True
        return False

    # ------------------------------------------------------------------
    # Random show
    # ------------------------------------------------------------------
    async def async_random_show(self) -> bool:
        import random as _random
        month = _random.randint(1, 12)
        day = _random.randint(1, 28)

        shows = await self.client.search_today_in_history(
            collections=self.collections,
            month=month,
            day=day,
            favored_taper=self.favored_taper,
        )
        attempts = 0
        while not shows and attempts < 5:
            month = _random.randint(1, 12)
            day = _random.randint(1, 28)
            shows = await self.client.search_today_in_history(
                collections=self.collections,
                month=month,
                day=day,
            )
            attempts += 1

        if shows:
            self.selected_month = month
            self.selected_day = day
            self.available_shows = shows
            self.current_show_index = 0
            self.available_tapers = []
            self.current_taper_index = 0
            self.current_tracks = []
            self.current_track_index = 0
            self.async_update_listeners()
            return True
        return False
