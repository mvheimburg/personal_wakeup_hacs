from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .alarm import WakeupAlarmEntity
from .const import (
    DATA_ALARM_ENTITIES,
    DATA_SERVICES_REGISTERED,
    DOMAIN,
    SERVICE_SET_CONFIG,
    SERVICE_TRIGGER_NOW,
)

_LOGGER = logging.getLogger(__name__)

SET_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional("enabled"): cv.boolean,
        vol.Optional("time_of_day"): vol.Any(cv.time, cv.string),
        vol.Optional("fade_duration"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("volume"): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=1)
        ),
        vol.Optional("playlist"): cv.string,
        vol.Optional("require_home"): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

TRIGGER_NOW_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
    },
    extra=vol.PREVENT_EXTRA,
)


def _get_entities(hass: HomeAssistant) -> dict[str, WakeupAlarmEntity]:
    """Return runtime entity registry for this integration."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    return domain_data.setdefault(DATA_ALARM_ENTITIES, {})


def _resolve_target_entity(
    hass: HomeAssistant, service_data: dict
) -> WakeupAlarmEntity | None:
    """Resolve a service target from entity_id or single-entity fallback."""
    entities = _get_entities(hass)
    if not entities:
        _LOGGER.warning("No Personal Wakeup entities available for service call")
        return None

    entity_id = service_data.get(ATTR_ENTITY_ID)
    if entity_id:
        for entity in entities.values():
            if entity.entity_id == entity_id:
                return entity

        _LOGGER.warning(
            "Ignoring Personal Wakeup service call for unknown entity_id=%s",
            entity_id,
        )
        return None

    if len(entities) == 1:
        return next(iter(entities.values()))

    _LOGGER.warning(
        "Ignoring Personal Wakeup service call without entity_id because multiple entities exist"
    )
    return None


def _register_services_once(hass: HomeAssistant) -> None:
    """Register integration services exactly once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_SERVICES_REGISTERED):
        return

    async def handle_set_config(call: ServiceCall) -> None:
        target = _resolve_target_entity(hass, dict(call.data))
        if target is None:
            return

        data = dict(call.data)
        data.pop(ATTR_ENTITY_ID, None)
        await target.async_set_config(data)

    async def handle_trigger_now(call: ServiceCall) -> None:
        target = _resolve_target_entity(hass, dict(call.data))
        if target is None:
            return
        await target.async_trigger()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CONFIG,
        handle_set_config,
        schema=SET_CONFIG_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRIGGER_NOW,
        handle_trigger_now,
        schema=TRIGGER_NOW_SCHEMA,
    )

    domain_data[DATA_SERVICES_REGISTERED] = True


def _unregister_services_if_unused(hass: HomeAssistant) -> None:
    """Unregister integration services when no entities are left."""
    domain_data = hass.data.get(DOMAIN, {})
    entities = domain_data.get(DATA_ALARM_ENTITIES, {})
    if entities:
        return

    if domain_data.get(DATA_SERVICES_REGISTERED):
        hass.services.async_remove(DOMAIN, SERVICE_SET_CONFIG)
        hass.services.async_remove(DOMAIN, SERVICE_TRIGGER_NOW)
        domain_data[DATA_SERVICES_REGISTERED] = False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Personal Wakeup alarm entity from a config entry."""
    entity = WakeupAlarmEntity(hass, entry)
    async_add_entities([entity])
    _get_entities(hass)[entry.entry_id] = entity
    _register_services_once(hass)

    def _on_unload() -> None:
        entities = _get_entities(hass)
        entities.pop(entry.entry_id, None)
        _unregister_services_if_unused(hass)

    entry.async_on_unload(_on_unload)
