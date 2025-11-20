from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, time, timedelta
import logging

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, CONF_REQUIRE_HOME, CONF_PERSON_ENTITY

_LOGGER = logging.getLogger(__name__)


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
    """Set up the wakeup alarm entity and register services."""
    _LOGGER.info("Setting up Personal Wakeup for entry %s", entry.entry_id)

    entity = WakeupAlarmEntity(hass, entry)
    async_add_entities([entity])

    async def handle_set_config(call: ServiceCall) -> None:
        _LOGGER.debug(
            "personal_wakeup.set_config called: data=%s", dict(call.data)
        )
        # In future you might support multiple entities per config entry via entity_id,
        # for now we ignore entity_id and always apply to this entity.
        data = dict(call.data)
        data.pop(ATTR_ENTITY_ID, None)
        await entity.async_set_config(data)

    async def handle_trigger_now(call: ServiceCall) -> None:
        _LOGGER.info(
            "personal_wakeup.trigger_now called for entry_id=%s, data=%s",
            entry.entry_id,
            dict(call.data),
        )
        await entity.async_trigger()

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

    _LOGGER.info("Personal Wakeup services registered for entry %s", entry.entry_id)


class WakeupAlarmEntity(Entity):
    """Single wakeup alarm entity for this config entry."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        alarm_name = entry.options.get(CONF_NAME, "Wakeup Alarm")
        self._attr_name = alarm_name
        self._attr_unique_id = f"{entry.entry_id}_{alarm_name.lower().replace(' ', '_')}"

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

        _LOGGER.debug(
            "WakeupAlarmEntity init: entry_id=%s options=%s config=%s",
            entry.entry_id,
            dict(entry.options),
            asdict(self._config),
        )

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
        _LOGGER.info(
            "WakeupAlarmEntity added to hass (entry_id=%s, entity_id=%s)",
            self._entry.entry_id,
            self.entity_id,
        )
        await self._reschedule()
        self.async_write_ha_state()

    async def async_set_config(self, data: dict) -> None:
        """Update runtime config from the frontend service."""
        _LOGGER.debug(
            "async_set_config called for %s with data=%s (before=%s)",
            self.entity_id,
            data,
            asdict(self._config),
        )

        # Accept partial updates from the UI card
        if "enabled" in data:
            self._config.enabled = bool(data["enabled"])

        if "time_of_day" in data:
            try:
                hh, mm = map(int, str(data["time_of_day"]).split(":"))
                self._config.time_of_day = time(hour=hh, minute=mm)
            except Exception as exc:
                _LOGGER.error(
                    "Invalid time_of_day %r in async_set_config for %s: %s",
                    data["time_of_day"],
                    self.entity_id,
                    exc,
                )

        if "fade_duration" in data:
            try:
                self._config.fade_duration = int(data["fade_duration"])
            except Exception as exc:
                _LOGGER.error(
                    "Invalid fade_duration %r in async_set_config for %s: %s",
                    data["fade_duration"],
                    self.entity_id,
                    exc,
                )

        if "volume" in data:
            try:
                self._config.volume = float(data["volume"])
            except Exception as exc:
                _LOGGER.error(
                    "Invalid volume %r in async_set_config for %s: %s",
                    data["volume"],
                    self.entity_id,
                    exc,
                )

        if "playlist" in data:
            self._config.playlist = str(data["playlist"])

        # 🔹 apply presence settings coming from the GUI
        if "require_home" in data:
            self._require_home = bool(data["require_home"])
            _LOGGER.debug(
                "require_home updated for %s -> %s",
                self.entity_id,
                self._require_home,
            )

        _LOGGER.debug(
            "Config after async_set_config for %s: %s (require_home=%s)",
            self.entity_id,
            asdict(self._config),
            self._require_home,
        )

        await self._reschedule()
        self.async_write_ha_state()

    async def _reschedule(self) -> None:
        """Compute next fire time and schedule callback."""
        from homeassistant.helpers.event import async_track_point_in_time
        from homeassistant.util import dt as dt_util

        _LOGGER.debug(
            "Rescheduling wakeup alarm for %s (enabled=%s, current next_fire=%s)",
            self.entity_id,
            self._config.enabled,
            self._next_fire,
        )

        # cancel previous listener if any
        if self._unsubscribe is not None:
            _LOGGER.debug("Cancelling previous scheduled callback for %s", self.entity_id)
            self._unsubscribe()
            self._unsubscribe = None

        if not self._config.enabled:
            _LOGGER.info("Wakeup alarm %s disabled; clearing next_fire", self.entity_id)
            self._next_fire = None
            self._state = "disarmed"
            return

        now_utc = dt_util.utcnow()
        local_now = dt_util.as_local(now_utc)

        # Make today_fire timezone-aware using the same tzinfo as local_now
        today_fire = datetime.combine(
            local_now.date(),
            self._config.time_of_day,
            tzinfo=local_now.tzinfo,
        )

        if today_fire <= local_now:
            today_fire += timedelta(days=1)

        # store as UTC
        self._next_fire = dt_util.as_utc(today_fire)
        self._state = "armed"

        _LOGGER.info(
            "Wakeup alarm %s scheduled: local=%s utc=%s",
            self.entity_id,
            today_fire,
            self._next_fire,
        )

        async def _cb(_now: datetime) -> None:
            _LOGGER.info(
                "Wakeup alarm callback fired for %s at %s", self.entity_id, _now
            )
            await self._run_alarm()

        self._unsubscribe = async_track_point_in_time(
            self.hass, _cb, self._next_fire
        )


    async def _run_alarm(self) -> None:
        """Execute the wakeup sequence if allowed by presence."""
        _LOGGER.info(
            "Running wakeup alarm for %s (require_home=%s person_entity=%s)",
            self.entity_id,
            self._require_home,
            self._person_entity,
        )

        # presence gate
        if self._require_home and self._person_entity:
            person_state = self.hass.states.get(self._person_entity)
            _LOGGER.debug(
                "Presence check for %s: state=%s",
                self._person_entity,
                person_state.state if person_state else None,
            )
            if not person_state or person_state.state != "home":
                # user not home -> skip alarm, but still reschedule
                _LOGGER.info(
                    "Skipping wakeup alarm for %s because %s is not home",
                    self.entity_id,
                    self._person_entity,
                )
                self._state = "skipped"
                self.async_write_ha_state()
                await self._reschedule()
                return

        self._state = "triggered"
        self.async_write_ha_state()
        _LOGGER.info("Wakeup alarm TRIGGERED for %s", self.entity_id)

        try:
            await self._fade_light()
        except Exception as exc:
            _LOGGER.error(
                "Error while fading light for %s: %s", self.entity_id, exc
            )

        try:
            await self._start_music()
        except Exception as exc:
            _LOGGER.error(
                "Error while starting music for %s: %s", self.entity_id, exc
            )

        # reschedule for next day
        await self._reschedule()
        self.async_write_ha_state()

    async def _fade_light(self) -> None:
        """Fade the configured light up over fade_duration."""
        light_entity = self._entry.options.get("light_entity")
        if not light_entity:
            _LOGGER.warning(
                "No light_entity configured in options for %s; skipping light fade",
                self.entity_id,
            )
            return

        _LOGGER.info(
            "Fading light %s for %s over %s seconds",
            light_entity,
            self.entity_id,
            self._config.fade_duration,
        )
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
        """Start playlist using Music Assistant."""
        player_entity = self._entry.options.get("ma_player_entity")
        playlist_uri = self._config.playlist

        if not player_entity:
            _LOGGER.warning(
                "No ma_player_entity configured in options for %s; skipping music",
                self.entity_id,
            )
            return

        _LOGGER.info(
            "Starting playlist %r on %s for %s",
            playlist_uri,
            player_entity,
            self.entity_id,
        )

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
        """Manually trigger the alarm (service call)."""
        _LOGGER.info("Manual trigger of wakeup alarm for %s", self.entity_id)
        await self._run_alarm()
