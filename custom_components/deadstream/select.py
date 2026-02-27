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

    def _show_options(self) -> list[str]:
        """Return stable display options; disambiguate duplicate labels."""
        shows = self.coordinator.available_shows
        base_labels = [self._show_label(i) for i in range(len(shows))]
        if not base_labels:
            return []

        counts: dict[str, int] = {}
        for label in base_labels:
            counts[label] = counts.get(label, 0) + 1

        used: dict[str, int] = {}
        options: list[str] = []
        for idx, label in enumerate(base_labels):
            if counts[label] <= 1:
                options.append(label)
                continue
            used[label] = used.get(label, 0) + 1
            ident = shows[idx].identifier
            short_id = ident[:10] if ident else str(used[label])
            options.append(f"{label} [{short_id}]")
        return options

    @property
    def options(self) -> list[str]:
        return self._show_options() or [_NO_SHOWS]

    @property
    def current_option(self) -> str | None:
        opts = self._show_options()
        if not opts:
            return None
        idx = self.coordinator.current_show_index
        n = len(opts)
        return opts[max(0, min(idx, n - 1))]

    async def async_select_option(self, option: str) -> None:
        opts = self._show_options()
        selected_idx: int | None = None

        if option in opts:
            selected_idx = opts.index(option)
        else:
            normalized = option.strip().lower()
            for idx, candidate in enumerate(opts):
                if candidate.strip().lower() == normalized:
                    selected_idx = idx
                    break

        if selected_idx is not None and 0 <= selected_idx < len(self.coordinator.available_shows):
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

    def _taper_options(self) -> list[str]:
        """Return stable taper options; disambiguate duplicate labels."""
        tapers = self.coordinator.available_tapers
        labels = [t.taper_label for t in tapers]
        if not labels:
            return []

        counts: dict[str, int] = {}
        for label in labels:
            counts[label] = counts.get(label, 0) + 1

        options: list[str] = []
        used: dict[str, int] = {}
        for idx, label in enumerate(labels):
            if counts[label] <= 1:
                options.append(label)
                continue
            used[label] = used.get(label, 0) + 1
            ident = tapers[idx].identifier
            short_id = ident[:10] if ident else str(used[label])
            options.append(f"{label} [{short_id}]")
        return options

    @property
    def options(self) -> list[str]:
        return self._taper_options() or [_NO_TAPERS]

    @property
    def current_option(self) -> str | None:
        opts = self._taper_options()
        if not opts:
            return None
        idx = self.coordinator.current_taper_index
        n = len(opts)
        return opts[max(0, min(idx, n - 1))]

    async def async_select_option(self, option: str) -> None:
        opts = self._taper_options()
        selected_idx: int | None = None

        if option in opts:
            selected_idx = opts.index(option)
        else:
            normalized = option.strip().lower()
            for idx, candidate in enumerate(opts):
                if candidate.strip().lower() == normalized:
                    selected_idx = idx
                    break

        if selected_idx is not None and 0 <= selected_idx < len(self.coordinator.available_tapers):
            self.coordinator.select_taper(selected_idx)

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
