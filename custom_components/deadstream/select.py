"""Select entities for Deadstream date, show, and taper navigation."""
from __future__ import annotations

import calendar
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeadstreamCoordinator

_LOGGER = logging.getLogger(__name__)

MONTHS = [calendar.month_name[m] for m in range(1, 13)]
DAYS = [str(d) for d in range(1, 32)]

_NO_SHOWS = "No shows available"
_NO_TAPERS = "Select a show first"
_NO_PLAYER = "(none)"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DeadstreamCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MonthSelect(coordinator, entry),
        DaySelect(coordinator, entry),
        ShowSelect(coordinator, entry),
        TaperSelect(coordinator, entry),
        TargetPlayerSelect(coordinator, entry),
    ])


class _DeadstreamSelect(CoordinatorEntity[DeadstreamCoordinator], SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DeadstreamCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}


class MonthSelect(_DeadstreamSelect):
    _attr_name = "Month"
    _attr_icon = "mdi:calendar-month"
    _attr_options = MONTHS

    def __init__(self, coordinator: DeadstreamCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "month")

    @property
    def current_option(self) -> str:
        return calendar.month_name[self.coordinator.selected_month]

    async def async_select_option(self, option: str) -> None:
        month = list(calendar.month_name).index(option)
        await self.coordinator.async_set_date(month, self.coordinator.selected_day)
        self.async_write_ha_state()


class DaySelect(_DeadstreamSelect):
    _attr_name = "Day"
    _attr_icon = "mdi:calendar-today"
    _attr_options = DAYS

    def __init__(self, coordinator: DeadstreamCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "day")

    @property
    def current_option(self) -> str:
        return str(self.coordinator.selected_day)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_date(self.coordinator.selected_month, int(option))
        self.async_write_ha_state()


class ShowSelect(_DeadstreamSelect):
    """One entry per year/collection for the selected month+day.

    Label format:
      Single band:  "1977 — Barton Hall, Cornell, NY"
      Multi-band:   "1977 GD — Barton Hall, Cornell, NY"
                    "1995 Phish — Madison Square Garden, NYC"
    """

    _attr_name = "Show"
    _attr_icon = "mdi:music-circle"

    def __init__(self, coordinator: DeadstreamCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "show")

    def _show_label(self, idx: int) -> str:
        s = self.coordinator.available_shows[idx]
        year = str(s.year or s.date[:4])
        # Use venue/city only — do NOT fall back to title, which often contains
        # taper-quality words ("Soundboard", "Audience") that belong in the Taper
        # dropdown, not the Show dropdown.
        loc = s.location
        multi_band = len(self.coordinator.collections) > 1
        if multi_band:
            short = _short_band(s.collection)
            base = f"{year} {short}"
        else:
            base = year
        return f"{base} \u2014 {loc}" if loc else base

    @property
    def options(self) -> list[str]:
        shows = self.coordinator.available_shows
        return [self._show_label(i) for i in range(len(shows))] or [_NO_SHOWS]

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.available_shows:
            return None
        idx = self.coordinator.current_show_index
        n = len(self.coordinator.available_shows)
        return self._show_label(max(0, min(idx, n - 1)))

    async def async_select_option(self, option: str) -> None:
        shows = self.coordinator.available_shows
        selected_idx: int | None = None
        normalized = option.strip()

        for idx in range(len(shows)):
            if self._show_label(idx).strip() == normalized:
                selected_idx = idx
                break

        # Fallback: case-insensitive match if UI formatting introduced subtle differences.
        if selected_idx is None:
            lower = normalized.lower()
            for idx in range(len(shows)):
                if self._show_label(idx).strip().lower() == lower:
                    selected_idx = idx
                    break

        if selected_idx is not None:
            await self.coordinator.async_select_show(selected_idx)

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class TaperSelect(_DeadstreamSelect):
    """All recordings for the currently selected show date, best-first.

    Populated automatically when a show is chosen in ShowSelect.
    The first option is the most-played recording (highest archive.org
    download count). Selecting a different entry swaps the active recording.
    """

    _attr_name = "Taper"
    _attr_icon = "mdi:microphone-variant"

    def __init__(self, coordinator: DeadstreamCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "taper_select")

    @property
    def options(self) -> list[str]:
        tapers = self.coordinator.available_tapers
        if not tapers:
            return [_NO_TAPERS]
        return [t.taper_label for t in tapers]

    @property
    def current_option(self) -> str | None:
        tapers = self.coordinator.available_tapers
        if not tapers:
            return None
        idx = self.coordinator.current_taper_index
        n = len(tapers)
        return tapers[max(0, min(idx, n - 1))].taper_label

    async def async_select_option(self, option: str) -> None:
        opts = self.options
        if option in opts:
            self.coordinator.select_taper(opts.index(option))
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class TargetPlayerSelect(_DeadstreamSelect):
    """Choose which media player receives the stream.

    Lists every media_player entity in HA. Select a media player group
    to broadcast to multiple speakers simultaneously.
    """

    _attr_name = "Target Player"
    _attr_icon = "mdi:cast-audio"

    def __init__(self, coordinator: DeadstreamCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "target_player")

    @property
    def options(self) -> list[str]:
        players = sorted(
            eid for eid in self.hass.states.async_entity_ids("media_player")
            if eid != "media_player.deadstream"
        )
        # Include the configured target even if HA hasn't loaded that entity yet.
        target = self.coordinator.target_player
        if target and target not in players:
            players = [target, *players]
        return [_NO_PLAYER, *players]

    @property
    def current_option(self) -> str:
        target = self.coordinator.target_player
        return target if target else _NO_PLAYER

    async def async_select_option(self, option: str) -> None:
        self.coordinator.target_player = None if option == _NO_PLAYER else option
        self.async_write_ha_state()


def _short_band(collection: str) -> str:
    """Return a short band abbreviation for multi-band show labels."""
    _ABBREVS = {
        "GratefulDead": "GD",
        "PhilLesh": "Phil",
        "BobWeir": "Weir",
        "JerryGarciaBand": "JGB",
        "OtherOnes": "OO",
        "TheOtherOnes": "TOO",
        "Phish": "Phish",
        "Goose": "Goose",
    }
    return _ABBREVS.get(collection, collection[:4])
