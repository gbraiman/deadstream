"""Sensor entities for Deadstream show/track info."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeadstreamCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DeadstreamCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VenueSensor(coordinator, entry), CurrentTrackSensor(coordinator, entry),
                        ShowCountSensor(coordinator, entry), TaperSensor(coordinator, entry)])


class _DeadstreamSensor(CoordinatorEntity[DeadstreamCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}


class VenueSensor(_DeadstreamSensor):
    _attr_name = "Venue"
    _attr_icon = "mdi:map-marker-music"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "venue")

    @property
    def native_value(self) -> str | None:
        show = self.coordinator.current_show
        return (show.location or show.title) if show else None


class CurrentTrackSensor(_DeadstreamSensor):
    _attr_name = "Current Track"
    _attr_icon = "mdi:music-note"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "current_track")

    @property
    def native_value(self) -> str | None:
        track = self.coordinator.current_track
        return track.title if track else None

    @property
    def extra_state_attributes(self) -> dict:
        track = self.coordinator.current_track
        if not track:
            return {}
        return {"track_number": track.track_num, "format": track.format, "duration_seconds": track.duration, "url": track.url}


class ShowCountSensor(_DeadstreamSensor):
    _attr_name = "Shows Available"
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "shows"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "show_count")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.available_shows)


class TaperSensor(_DeadstreamSensor):
    _attr_name = "Taper"
    _attr_icon = "mdi:microphone"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "taper")

    @property
    def native_value(self) -> str | None:
        show = self.coordinator.current_show
        return (show.taper or "Unknown") if show else None
