"""Config flow for Deadstream integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    AVAILABLE_COLLECTIONS,
    COLLECTION_LABELS,
    CONF_COLLECTIONS,
    CONF_DEFAULT_PLAYER,
    CONF_FAVORED_TAPER,
    CONF_PLAY_LOSSLESS,
    DEFAULT_COLLECTIONS,
    DEFAULT_FAVORED_TAPER,
    DEFAULT_PLAY_LOSSLESS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _build_schema(
    collections: list[str] | None = None,
    play_lossless: bool = DEFAULT_PLAY_LOSSLESS,
    favored_taper: str = DEFAULT_FAVORED_TAPER,
    default_player: str = "",
) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_COLLECTIONS, default=collections or DEFAULT_COLLECTIONS): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=c, label=COLLECTION_LABELS.get(c, c))
                    for c in AVAILABLE_COLLECTIONS
                ],
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Optional(CONF_DEFAULT_PLAYER, default=default_player): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="media_player")
        ),
        vol.Optional(CONF_PLAY_LOSSLESS, default=play_lossless): selector.BooleanSelector(),
        vol.Optional(CONF_FAVORED_TAPER, default=favored_taper): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
    })


class DeadstreamConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Deadstream."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Deadstream", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
            errors={},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    """Handle Deadstream options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage Deadstream options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options or self.config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(
                collections=current.get(CONF_COLLECTIONS, DEFAULT_COLLECTIONS),
                play_lossless=current.get(CONF_PLAY_LOSSLESS, DEFAULT_PLAY_LOSSLESS),
                favored_taper=current.get(CONF_FAVORED_TAPER, DEFAULT_FAVORED_TAPER),
                default_player=current.get(CONF_DEFAULT_PLAYER, ""),
            ),
        )
