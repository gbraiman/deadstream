"""The Deadstream integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_COLLECTIONS,
    CONF_DEFAULT_PLAYER,
    CONF_FAVORED_TAPER,
    CONF_PLAY_LOSSLESS,
    DEFAULT_COLLECTIONS,
    DEFAULT_FAVORED_TAPER,
    DEFAULT_PLAY_LOSSLESS,
    DOMAIN,
    SERVICE_NEXT_SHOW,
    SERVICE_PLAY_DATE,
    SERVICE_PREV_SHOW,
    SERVICE_RANDOM_SHOW,
    SERVICE_TODAY_IN_HISTORY,
)
from .coordinator import DeadstreamCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

SERVICE_PLAY_DATE_SCHEMA = vol.Schema({
    vol.Required("month"): vol.All(int, vol.Range(min=1, max=12)),
    vol.Required("day"): vol.All(int, vol.Range(min=1, max=31)),
})


def _get_coordinator(hass: HomeAssistant) -> DeadstreamCoordinator | None:
    """Return the first Deadstream coordinator."""
    coordinators = hass.data.get(DOMAIN, {})
    if coordinators:
        return next(iter(coordinators.values()))
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Deadstream from a config entry."""
    session = async_get_clientsession(hass)

    coordinator = DeadstreamCoordinator(
        hass=hass,
        session=session,
        collections=entry.options.get(CONF_COLLECTIONS, entry.data.get(CONF_COLLECTIONS, DEFAULT_COLLECTIONS)),
        play_lossless=entry.options.get(CONF_PLAY_LOSSLESS, entry.data.get(CONF_PLAY_LOSSLESS, DEFAULT_PLAY_LOSSLESS)),
        favored_taper=entry.options.get(CONF_FAVORED_TAPER, entry.data.get(CONF_FAVORED_TAPER, DEFAULT_FAVORED_TAPER)),
    )

    # Apply default player from config (user-chosen in options flow).
    default_player = entry.options.get(CONF_DEFAULT_PLAYER) or entry.data.get(CONF_DEFAULT_PLAYER, "")
    if default_player:
        coordinator.default_player = default_player
        coordinator.target_player = default_player
        _LOGGER.debug("Deadstream: default player set to %s", default_player)

    _LOGGER.info(
        "Deadstream starting — collections: %s, default_player: %s",
        coordinator.collections,
        coordinator.target_player or "(none)",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    if not hass.services.has_service(DOMAIN, SERVICE_PLAY_DATE):
        _register_services(hass)

    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register Deadstream services."""

    async def handle_play_date(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator:
            await coordinator.async_set_date(call.data["month"], call.data["day"])

    async def handle_next_show(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator:
            coordinator.next_show()
            await coordinator.async_load_tapers_for_current_show()
            coordinator.current_tracks = []
            coordinator.current_track_index = 0
            coordinator.async_update_listeners()

    async def handle_prev_show(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator:
            coordinator.prev_show()
            await coordinator.async_load_tapers_for_current_show()
            coordinator.current_tracks = []
            coordinator.current_track_index = 0
            coordinator.async_update_listeners()

    async def handle_random_show(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator:
            await coordinator.async_random_show()

    async def handle_today_in_history(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator:
            await coordinator.async_today_in_history()

    hass.services.async_register(DOMAIN, SERVICE_PLAY_DATE, handle_play_date, SERVICE_PLAY_DATE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_NEXT_SHOW, handle_next_show)
    hass.services.async_register(DOMAIN, SERVICE_PREV_SHOW, handle_prev_show)
    hass.services.async_register(DOMAIN, SERVICE_RANDOM_SHOW, handle_random_show)
    hass.services.async_register(DOMAIN, SERVICE_TODAY_IN_HISTORY, handle_today_in_history)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data.get(DOMAIN):
            for service in (
                SERVICE_PLAY_DATE,
                SERVICE_NEXT_SHOW,
                SERVICE_PREV_SHOW,
                SERVICE_RANDOM_SHOW,
                SERVICE_TODAY_IN_HISTORY,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
