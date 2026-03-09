"""The Personal Wakeup integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, DATA_CONFIG_ENTRIES, PLATFORMS


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up from YAML (unused)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Personal Wakeup from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    config_entries = domain_data.setdefault(DATA_CONFIG_ENTRIES, {})
    config_entries[entry.entry_id] = entry

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
        domain_data = hass.data.get(DOMAIN, {})
        config_entries = domain_data.get(DATA_CONFIG_ENTRIES, {})
        config_entries.pop(entry.entry_id, None)
    return unload_ok
