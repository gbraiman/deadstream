"""DataUpdateCoordinator for Deadstream."""
from __future__ import annotations

import logging
from datetime import timedelta
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
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.client = ArchiveClient(session)
        self.collections: list[str] = collections or DEFAULT_COLLECTIONS
        self.play_lossless = play_lossless
        self.favored_taper = favored_taper

        # Browsing state
        self.selected_year: int = 1977
        self.selected_month: int = 5
        self.selected_day: int = 8
        self.available_shows: list[Show] = []
        self.current_show_index: int = 0

        # Playback state
        self.current_tracks: list[Track] = []
        self.current_track_index: int = 0
        self.is_playing: bool = False
        self.target_player: str | None = None

    @property
    def current_show(self) -> Show | None:
        """Return currently selected show."""
        if self.available_shows and 0 <= self.current_show_index < len(self.available_shows):
            return self.available_shows[self.current_show_index]
        return None

    @property
    def current_track(self) -> Track | None:
        """Return currently playing track."""
        if self.current_tracks and 0 <= self.current_track_index < len(self.current_tracks):
            return self.current_tracks[self.current_track_index]
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch shows for the currently selected date."""
        try:
            shows = await self.client.search_shows(
                collections=self.collections,
                year=self.selected_year,
                month=self.selected_month,
                day=self.selected_day,
                favored_taper=self.favored_taper,
            )
            self.available_shows = shows
            # Reset show index if out of bounds
            if self.current_show_index >= len(self.available_shows):
                self.current_show_index = 0
        except Exception as err:
            raise UpdateFailed(f"Error fetching shows: {err}") from err

        return {
            "shows": self.available_shows,
            "year": self.selected_year,
            "month": self.selected_month,
            "day": self.selected_day,
        }

    async def async_set_date(self, year: int, month: int, day: int) -> None:
        """Set the browsing date and refresh shows."""
        self.selected_year = year
        self.selected_month = month
        self.selected_day = day
        self.current_show_index = 0
        await self.async_refresh()

    async def async_load_show(self, show: Show) -> bool:
        """Load tracks for the given show."""
        tracks = await self.client.get_show_tracks(show.identifier, self.play_lossless)
        if not tracks:
            _LOGGER.warning("No tracks found for show %s", show.identifier)
            return False
        self.current_tracks = tracks
        self.current_track_index = 0
        return True

    async def async_load_current_show(self) -> bool:
        """Load tracks for the currently selected show."""
        show = self.current_show
        if not show:
            return False
        return await self.async_load_show(show)

    def next_show(self) -> bool:
        """Advance to the next available show for this date."""
        if not self.available_shows:
            return False
        self.current_show_index = (self.current_show_index + 1) % len(self.available_shows)
        return True

    def prev_show(self) -> bool:
        """Go to the previous available show for this date."""
        if not self.available_shows:
            return False
        self.current_show_index = (self.current_show_index - 1) % len(self.available_shows)
        return True

    def next_track(self) -> bool:
        """Advance to the next track."""
        if not self.current_tracks:
            return False
        if self.current_track_index < len(self.current_tracks) - 1:
            self.current_track_index += 1
            return True
        return False

    def prev_track(self) -> bool:
        """Go to the previous track."""
        if not self.current_tracks:
            return False
        if self.current_track_index > 0:
            self.current_track_index -= 1
            return True
        return False

    async def async_random_show(self) -> bool:
        """Select a random year/month/day and load shows."""
        import random as _random
        year = _random.randint(1967, 1995)
        month = _random.randint(1, 12)
        day = _random.randint(1, 28)

        shows = await self.client.search_shows(
            collections=self.collections,
            year=year,
            month=month,
            day=day,
            favored_taper=self.favored_taper,
        )
        # Retry up to 5 times if no shows found
        attempts = 0
        while not shows and attempts < 5:
            year = _random.randint(1967, 1995)
            month = _random.randint(1, 12)
            day = _random.randint(1, 28)
            shows = await self.client.search_shows(
                collections=self.collections,
                year=year,
                month=month,
                day=day,
            )
            attempts += 1

        if shows:
            self.selected_year = year
            self.selected_month = month
            self.selected_day = day
            self.available_shows = shows
            self.current_show_index = 0
            self.async_update_listeners()
            return True
        return False
