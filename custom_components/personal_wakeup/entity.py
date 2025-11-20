from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


@dataclass
class WakeupConfig:
    time_of_day: time
    enabled: bool
    fade_duration: int  # seconds
    volume: float
    playlist: str


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    entity = WakeupAlarmEntity(hass, entry)
    async_add_entities([entity])

    async def handle_set_config(call: ServiceCall) -> None:
        await entity.async_set_config(call.data)

    hass.services.async_register(
        DOMAIN,
        "set_config",
        handle_set_config,
    )


class WakeupAlarmEntity(Entity):
    """Single wakeup alarm entity for this config entry."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_name = "Wakeup Alarm"

        self._config = WakeupConfig(
            time_of_day=time(7, 0),
            enabled=True,
            fade_duration=900,
            volume=0.25,
            playlist="morning_chill",
        )
        self._next_fire: datetime | None = None
        self._state: str = "disarmed"

        # Optional: device tracker constraint
        # Expect these to be provided in entry.options, e.g. from config_flow:
        #   options["device_tracker_entity"] = "device_tracker.phone"
        #   options["require_home"] = True
        self._device_tracker_entity: str | None = entry.options.get(
            "device_tracker_entity"
        )
        self._require_home: bool = bool(entry.options.get("require_home", False))

    @property
    def state(self) -> str:
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "enabled": self._config.enabled,
            "time_of_day": self._config.time_of_day.isoformat(),
            "fade_duration": self._config.fade_duration,
            "volume": self._config.volume,
            "playlist": self._config.playlist,
            "next_fire": self._next_fire.isoformat() if self._next_fire else None,
            "device_tracker_entity": self._device_tracker_entity,
            "require_home": self._require_home,
        }

    async def async_added_to_hass(self) -> None:
        await self._reschedule()

    async def async_set_config(self, data: dict) -> None:
        """Accept partial updates from the UI card or service."""
        if "enabled" in data:
            self._config.enabled = bool(data["enabled"])

        if "time_of_day" in data:
            # expects "HH:MM"
            hh, mm = map(int, str(data["time_of_day"]).split(":"))
            self._config.time_of_day = time(hour=hh, minute=mm)

        if "fade_duration" in data:
            self._config.fade_duration = int(data["fade_duration"])

        if "volume" in data:
            self._config.volume = float(data["volume"])

        if "playlist" in data:
            self._config.playlist = str(data["playlist"])

        # Allow changing device tracker + require_home via config service too (optional)
        if "device_tracker_entity" in data:
            value = data["device_tracker_entity"]
            self._device_tracker_entity = str(value) if value else None

        if "require_home" in data:
            self._require_home = bool(data["require_home"])

        await self._reschedule()
        self.async_write_ha_state()

    async def _reschedule(self) -> None:
        """Schedule the next alarm run based on current config."""
        from homeassistant.helpers.event import async_track_point_in_time  # lazy import

        # cancel previous listener if you keep a handle (not stored yet in this version)
        if not self._config.enabled:
            self._next_fire = None
            self._state = "disarmed"
            return

        now = datetime.now()
        today_fire = datetime.combine(now.date(), self._config.time_of_day)
        if today_fire <= now:
            today_fire += timedelta(days=1)

        self._next_fire = today_fire
        self._state = "armed"

        async def _cb(_now: datetime) -> None:
            await self._run_alarm()

        async_track_point_in_time(self.hass, _cb, today_fire)

    async def _run_alarm(self) -> None:
        """Check preconditions and trigger the alarm sequence (light + music)."""

        # If we require the device to be home, check device_tracker state
        if self._require_home and self._device_tracker_entity:
            tracker_state = self.hass.states.get(self._device_tracker_entity)
            if not tracker_state or tracker_state.state != "home":
                # Device not home → skip this run, reschedule for next day
                self._state = "waiting_for_home"
                self.async_write_ha_state()
                await self._reschedule()
                return

        self._state = "triggered"
        self.async_write_ha_state()

        # Do the light fade + music via services; you can call Music Assistant here
        await self._fade_light()
        await self._start_music()

        # Reschedule for the next day
        await self._reschedule()

    async def _fade_light(self) -> None:
        # Example: use a fixed light/entity from entry.options
        light_entity = self._entry.options["light_entity"]
        await self.hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {
                "entity_id": light_entity,
                "brightness": 255,
                "transition": self._config.fade_duration,
            },
            blocking=False,
        )

    async def _start_music(self) -> None:
        player_entity = self._entry.options["ma_player_entity"]
        playlist_uri = self._config.playlist

        # Example: Music Assistant
        await self.hass.services.async_call(
            "music_assistant",
            "play_media",
            {
                "entity_id": player_entity,
                "media_id": playlist_uri,
                "media_type": "playlist",
                "enqueue": "replace",
            },
            blocking=False,
        )
