from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, CONF_REQUIRE_HOME, CONF_PERSON_ENTITY


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

        # options from config entry (person / require_home)
        self._person_entity: str | None = entry.options.get(CONF_PERSON_ENTITY)
        self._require_home: bool = bool(
            entry.options.get(CONF_REQUIRE_HOME, False)
        )

        self._unsubscribe = None  # handle from async_track_point_in_time

    @property
    def state(self) -> str:
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "enabled": self._config.enabled,
            "time_of_day": self._config.time_of_day.isoformat(timespec="minutes"),
            "fade_duration": self._config.fade_duration,
            "volume": self._config.volume,
            "playlist": self._config.playlist,
            "next_fire": self._next_fire.isoformat() if self._next_fire else None,
            "require_home": self._require_home,
            "person_entity": self._person_entity,
        }

    async def async_added_to_hass(self) -> None:
        await self._reschedule()

    async def async_set_config(self, data: dict) -> None:
        """Update runtime config from the frontend service."""
        # Accept partial updates from the UI card
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

        # re-read require_home/person from options if you want them editable later

        # 🔴 This is the important part:
        await self._reschedule()
        self.async_write_ha_state()

    async def _reschedule(self) -> None:
        """Compute next fire time and schedule callback."""
        from homeassistant.helpers.event import async_track_point_in_time
        from homeassistant.util import dt as dt_util

        # cancel previous listener if any
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

        if not self._config.enabled:
            self._next_fire = None
            self._state = "disarmed"
            return

        now = dt_util.utcnow()
        # convert to local date for the time-of-day
        local_now = dt_util.as_local(now)
        today_fire = datetime.combine(local_now.date(), self._config.time_of_day)
        if today_fire <= local_now:
            today_fire += timedelta(days=1)

        # store as UTC
        self._next_fire = dt_util.as_utc(today_fire)
        self._state = "armed"

        async def _cb(_now: datetime) -> None:
            await self._run_alarm()

        self._unsubscribe = async_track_point_in_time(
            self.hass, _cb, self._next_fire
        )


    async def _run_alarm(self) -> None:
        """Execute the wakeup sequence if allowed by presence."""
        # presence gate
        if self._require_home and self._person_entity:
            person_state = self.hass.states.get(self._person_entity)
            if not person_state or person_state.state != "home":
                # user not home -> skip alarm, but still reschedule
                self._state = "skipped"
                self.async_write_ha_state()
                await self._reschedule()
                return

        self._state = "triggered"
        self.async_write_ha_state()

        await self._fade_light()
        await self._start_music()

        # reschedule for next day
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


    async def async_trigger(self) -> None:
        await self._run_alarm()
