"""Switch entities for toggling archive.org collections (bands) in Deadstream."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AVAILABLE_COLLECTIONS, COLLECTION_LABELS, CONF_COLLECTIONS, DEFAULT_COLLECTIONS, DOMAIN
from .coordinator import DeadstreamCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one switch per band that the user has configured."""
    coordinator: DeadstreamCoordinator = hass.data[DOMAIN][entry.entry_id]
    configured = entry.options.get(
        CONF_COLLECTIONS, entry.data.get(CONF_COLLECTIONS, DEFAULT_COLLECTIONS)
    )

    # Remove stale entity registry entries for bands that are no longer configured.
    # Iterate directly over every registry entry for this config_entry_id — more
    # reliable than async_get_entity_id, which silently returns None on any mismatch.
    ent_reg = er.async_get(hass)
    prefix = f"{entry.entry_id}_collection_"
    stale = [
        reg_entry
        for reg_entry in list(ent_reg.entities.values())
        if reg_entry.config_entry_id == entry.entry_id
        and reg_entry.domain == "switch"
        and reg_entry.unique_id.startswith(prefix)
        and reg_entry.unique_id[len(prefix):] in {c.lower() for c in AVAILABLE_COLLECTIONS}
        and next(
            (c for c in AVAILABLE_COLLECTIONS if c.lower() == reg_entry.unique_id[len(prefix):]),
            None,
        ) not in configured
    ]
    for reg_entry in stale:
        _LOGGER.info("Removing stale switch entity: %s (%s)", reg_entry.entity_id, reg_entry.unique_id)
        ent_reg.async_remove(reg_entry.entity_id)

    async_add_entities(
        CollectionSwitch(coordinator, entry, collection)
        for collection in AVAILABLE_COLLECTIONS
        if collection in configured
    )


class CollectionSwitch(CoordinatorEntity[DeadstreamCoordinator], SwitchEntity):
    """Toggle a single archive.org collection on/off.

    Turning a band off removes it from the search; turning it on adds it back.
    At least one collection must remain active — the last one cannot be turned off.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DeadstreamCoordinator,
        entry: ConfigEntry,
        collection: str,
    ) -> None:
        super().__init__(coordinator)
        self._collection = collection
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_collection_{collection.lower()}"
        self._attr_name = COLLECTION_LABELS.get(collection, collection)
        self._attr_icon = "mdi:music-note-plus"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def is_on(self) -> bool:
        return self._collection in self.coordinator.collections

    async def async_turn_on(self, **kwargs) -> None:
        if self._collection not in self.coordinator.collections:
            self.coordinator.collections = [*self.coordinator.collections, self._collection]
            await self.coordinator.async_refresh()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        if len(self.coordinator.collections) <= 1:
            _LOGGER.warning(
                "Cannot disable %s — at least one collection must remain active.",
                self._collection,
            )
            return
        self.coordinator.collections = [
            c for c in self.coordinator.collections if c != self._collection
        ]
        await self.coordinator.async_refresh()
        self.async_write_ha_state()
