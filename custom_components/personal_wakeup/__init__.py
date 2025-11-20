"""The Personal Wakeup integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up from YAML (unused)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Personal Wakeup from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload entities when options change
    entry.async_on_unload(
        entry.add_update_listener(config_entry_update_listener)
    )

    return True


async def config_entry_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Handle config entry options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
