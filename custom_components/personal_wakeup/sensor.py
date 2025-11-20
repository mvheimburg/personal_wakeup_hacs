from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .alarm import WakeupAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Personal Wakeup alarm entity from a config entry."""
    entity = WakeupAlarmEntity(hass, entry)
    async_add_entities([entity])

    async def handle_set_config(call: ServiceCall) -> None:
        # allow entity_id param for future multi-entity support, but ignore for now
        await entity.async_set_config(call.data)

    async def handle_trigger_now(call: ServiceCall) -> None:
        await entity.async_trigger()

    # Register services under integration domain
    hass.services.async_register(
        DOMAIN,
        "set_config",
        handle_set_config,
    )

    hass.services.async_register(
        DOMAIN,
        "trigger_now",
        handle_trigger_now,
    )
