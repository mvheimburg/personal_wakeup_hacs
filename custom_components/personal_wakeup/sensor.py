"""Sensor platform for Personal Wakeup integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Personal Wakeup sensor."""
    async_add_entities([PersonalWakeupStatusSensor(entry)])


class PersonalWakeupStatusSensor(SensorEntity):
    """Simple sensor reflecting the wakeup alarm status."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_name = "Wakeup Alarm Status"
        self._attr_native_value = "idle"

    @property
    def should_poll(self) -> bool:
        return False
