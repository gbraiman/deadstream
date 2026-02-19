"""Select entities for Deadstream date and show navigation."""
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

import datetime
YEARS = [str(y) for y in range(1965, datetime.date.today().year + 1)]
MONTHS = [calendar.month_name[m] for m in range(1, 13)]
DAYS = [str(d) for d in range(1, 32)]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DeadstreamCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([YearSelect(coordinator, entry), MonthSelect(coordinator, entry),
                        DaySelect(coordinator, entry), ShowSelect(coordinator, entry)])


class _DeadstreamSelect(CoordinatorEntity[DeadstreamCoordinator], SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}


class YearSelect(_DeadstreamSelect):
    _attr_name = "Year"
    _attr_icon = "mdi:calendar-range"
    _attr_options = YEARS

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "year")

    @property
    def current_option(self) -> str:
        return str(self.coordinator.selected_year)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_date(int(option), self.coordinator.selected_month, self.coordinator.selected_day)
        self.async_write_ha_state()


class MonthSelect(_DeadstreamSelect):
    _attr_name = "Month"
    _attr_icon = "mdi:calendar-month"
    _attr_options = MONTHS

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "month")

    @property
    def current_option(self) -> str:
        return calendar.month_name[self.coordinator.selected_month]

    async def async_select_option(self, option: str) -> None:
        month = list(calendar.month_name).index(option)
        await self.coordinator.async_set_date(self.coordinator.selected_year, month, self.coordinator.selected_day)
        self.async_write_ha_state()


class DaySelect(_DeadstreamSelect):
    _attr_name = "Day"
    _attr_icon = "mdi:calendar-today"
    _attr_options = DAYS

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "day")

    @property
    def current_option(self) -> str:
        return str(self.coordinator.selected_day)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_date(self.coordinator.selected_year, self.coordinator.selected_month, int(option))
        self.async_write_ha_state()


class ShowSelect(_DeadstreamSelect):
    _attr_name = "Show"
    _attr_icon = "mdi:music-circle"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "show")

    @property
    def options(self) -> list[str]:
        shows = self.coordinator.available_shows
        if not shows:
            return ["No shows available"]
        return [f"{i + 1}. {s.location} ({s.taper or 'unknown taper'})" for i, s in enumerate(shows)]

    @property
    def current_option(self) -> str:
        shows = self.coordinator.available_shows
        idx = self.coordinator.current_show_index
        if shows and 0 <= idx < len(shows):
            s = shows[idx]
            return f"{idx + 1}. {s.location} ({s.taper or 'unknown taper'})"
        return "No shows available"

    async def async_select_option(self, option: str) -> None:
        for i, opt in enumerate(self.options):
            if opt == option:
                self.coordinator.current_show_index = i
                self.coordinator.current_tracks = []
                self.coordinator.current_track_index = 0
                self.coordinator.async_update_listeners()
                self.async_write_ha_state()
                return

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
