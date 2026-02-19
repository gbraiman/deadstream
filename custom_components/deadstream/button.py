"""Button entities for Deadstream show navigation."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeadstreamCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DeadstreamCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NextShowButton(coordinator, entry), PrevShowButton(coordinator, entry),
                        RandomShowButton(coordinator, entry), LoadShowButton(coordinator, entry)])


class _DeadstreamButton(CoordinatorEntity[DeadstreamCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}


class NextShowButton(_DeadstreamButton):
    _attr_name = "Next Show"
    _attr_icon = "mdi:skip-next-circle"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "next_show")

    async def async_press(self) -> None:
        self.coordinator.next_show()
        self.coordinator.current_tracks = []
        self.coordinator.current_track_index = 0
        self.coordinator.async_update_listeners()


class PrevShowButton(_DeadstreamButton):
    _attr_name = "Previous Show"
    _attr_icon = "mdi:skip-previous-circle"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "prev_show")

    async def async_press(self) -> None:
        self.coordinator.prev_show()
        self.coordinator.current_tracks = []
        self.coordinator.current_track_index = 0
        self.coordinator.async_update_listeners()


class RandomShowButton(_DeadstreamButton):
    _attr_name = "Random Show"
    _attr_icon = "mdi:shuffle-variant"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "random_show")

    async def async_press(self) -> None:
        await self.coordinator.async_random_show()


class LoadShowButton(_DeadstreamButton):
    _attr_name = "Load Show"
    _attr_icon = "mdi:playlist-play"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "load_show")

    async def async_press(self) -> None:
        await self.coordinator.async_load_current_show()
        self.coordinator.async_update_listeners()
