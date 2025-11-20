"""Config flow for the Personal Wakeup integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import selector

from .const import (
    DOMAIN,
    CONF_LIGHT_ENTITY,
    CONF_MA_PLAYER_ENTITY,
    CONF_PERSON_ENTITY,
    CONF_REQUIRE_HOME,
)

DEFAULT_NAME = "Wakeup Alarm"
DEFAULT_REQUIRE_HOME = False


def _base_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME,
                default=defaults.get(CONF_NAME, DEFAULT_NAME),
            ): str,
            vol.Required(
                CONF_LIGHT_ENTITY,
                default=defaults.get(CONF_LIGHT_ENTITY),
            ): selector({"entity": {"domain": "light"}}),
            vol.Required(
                CONF_MA_PLAYER_ENTITY,
                default=defaults.get(CONF_MA_PLAYER_ENTITY),
            ): selector({"entity": {"domain": "media_player"}}),
            vol.Optional(
                CONF_PERSON_ENTITY,
                default=defaults.get(CONF_PERSON_ENTITY),
            ): selector({"entity": {"domain": "person"}}),
            vol.Required(
                CONF_REQUIRE_HOME,
                default=defaults.get(CONF_REQUIRE_HOME, DEFAULT_REQUIRE_HOME),
            ): selector({"boolean": {}}),
        }
    )


class PersonalWakeupConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Personal Wakeup."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_LIGHT_ENTITY):
                errors["base"] = "no_light_entity"
            elif not user_input.get(CONF_MA_PLAYER_ENTITY):
                errors["base"] = "no_player_entity"
            else:
                name = user_input[CONF_NAME]
                options = {
                    k: v
                    for k, v in user_input.items()
                    if k != CONF_NAME
                }

                return self.async_create_entry(
                    title=name,
                    data={},
                    options=options,
                )

        defaults: dict[str, Any] = {CONF_NAME: DEFAULT_NAME}
        return self.async_show_form(
            step_id="user",
            data_schema=_base_schema(defaults),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "PersonalWakeupOptionsFlow":
        return PersonalWakeupOptionsFlow(config_entry)


class PersonalWakeupOptionsFlow(OptionsFlow):
    """Handle options for Personal Wakeup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_LIGHT_ENTITY):
                errors["base"] = "no_light_entity"
            elif not user_input.get(CONF_MA_PLAYER_ENTITY):
                errors["base"] = "no_player_entity"
            else:
                name = user_input.get(CONF_NAME) or self._entry.title
                options = {
                    k: v
                    for k, v in user_input.items()
                    if k != CONF_NAME
                }

                return self.async_create_entry(
                    title=name,
                    data=options,
                )

        current = {**self._entry.options}
        current.setdefault(CONF_NAME, self._entry.title)
        current.setdefault(CONF_REQUIRE_HOME, DEFAULT_REQUIRE_HOME)

        return self.async_show_form(
            step_id="init",
            data_schema=_base_schema(current),
            errors=errors,
        )
