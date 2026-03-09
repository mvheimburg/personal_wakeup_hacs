from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, asdict
from datetime import datetime, time, timedelta
import logging

import asyncio

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.util import slugify

from .const import (
    CONF_LIGHT_ENTITY,
    CONF_MA_PLAYER_ENTITY,
    CONF_PLAYLIST_OPTIONS,
    CONF_PERSON_ENTITY,
    CONF_REQUIRE_HOME,
    DEFAULT_SNOOZE_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class WakeupConfig:
    time_of_day: time
    enabled: bool
    fade_duration: int  # seconds
    volume: float
    playlist: str
    fade_music_duration: int = 300  # seconds


class WakeupAlarmEntity(Entity):
    """Single wakeup alarm entity for this config entry."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        playlist_options = entry.options.get(CONF_PLAYLIST_OPTIONS, [])
        if not isinstance(playlist_options, list):
            playlist_options = []
        default_playlist = playlist_options[0] if playlist_options else ""

        person_entity: str | None = entry.options.get(CONF_PERSON_ENTITY)
        pretty_person: str | None = None
        if person_entity and "." in person_entity:
            # "person.matilde" -> "matilde" -> "Matilde"
            pretty_person = person_entity.split(".", 1)[1].replace("_", " ").title()

        if pretty_person:
            friendly_name = f"{pretty_person} wakeup"
        else:
            # fall back to entry title or generic
            friendly_name = entry.title or "Wakeup Alarm"

        # This is what shows up in the UI:
        self._attr_name = friendly_name
        safe = slugify(friendly_name)  # e.g. "Matilde wakeup" -> "matilde_wakeup"
        self._attr_unique_id = f"{entry.entry_id}_{safe}"

        self._config = WakeupConfig(
            time_of_day=time(7, 0),
            enabled=True,
            fade_duration=900,
            volume=0.25,
            playlist=default_playlist,
        )
        self._next_fire: datetime | None = None
        self._state: str = "disarmed"

        # options from config entry (person / require_home)
        self._person_entity: str | None = entry.options.get(CONF_PERSON_ENTITY)
        self._require_home: bool = bool(
            entry.options.get(CONF_REQUIRE_HOME, False)
        )

        self._unsubscribe = None  # handle from async_track_point_in_time
        # run state / cancellation
        self._running: bool = False
        self._cancel_requested: bool = False
        self._run_task: asyncio.Task | None = None

        _LOGGER.debug(
            "WakeupAlarmEntity init: entry_id=%s options=%s config=%s",
            entry.entry_id,
            dict(entry.options),
            asdict(self._config),
        )

    @property
    def state(self) -> str:
        return self._state

    def _playlist_options(self) -> list[str]:
        raw = self._entry.options.get(CONF_PLAYLIST_OPTIONS, [])
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        playlist_options = self._playlist_options()

        return {
            "enabled": self._config.enabled,
            "time_of_day": self._config.time_of_day.isoformat(timespec="minutes"),
            "fade_duration": self._config.fade_duration,
            "volume": self._config.volume,
            "playlist": self._config.playlist,
            "playlist_options": playlist_options,
            "next_fire": self._next_fire.isoformat() if self._next_fire else None,
            "require_home": self._require_home,
            "person_entity": self._person_entity,
            "running": self._running,
            "can_snooze": self._running or self._state == "triggered",
            "can_stop": self._running or self._state in {"triggered", "snoozed"},
            "snooze_minutes": DEFAULT_SNOOZE_MINUTES,
        }

    async def async_added_to_hass(self) -> None:
        _LOGGER.info(
            "WakeupAlarmEntity added to hass (entry_id=%s, entity_id=%s)",
            self._entry.entry_id,
            self.entity_id,
        )
        await self._reschedule()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel runtime listeners/tasks before entity is removed."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

        self._cancel_requested = True
        run_task = self._run_task
        if run_task and not run_task.done() and run_task is not asyncio.current_task():
            run_task.cancel()
            with suppress(asyncio.CancelledError):
                await run_task

        self._next_fire = None
        self._state = "disarmed"

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
                raw_time = data["time_of_day"]
                if isinstance(raw_time, time):
                    self._config.time_of_day = raw_time.replace(
                        second=0,
                        microsecond=0,
                    )
                else:
                    parts = str(raw_time).split(":")
                    hh, mm = map(int, parts[:2])
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
            playlist = str(data["playlist"]).strip()
            options = self._playlist_options()
            if options and playlist and playlist not in options:
                _LOGGER.warning(
                    "Ignoring unknown playlist %r for %s",
                    playlist,
                    self.entity_id,
                )
            elif options and not playlist:
                self._config.playlist = options[0]
            else:
                self._config.playlist = playlist

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
        await self._schedule_callback(
            dt_util.as_utc(today_fire),
            state="armed",
            ignore_presence=False,
        )

    async def _schedule_callback(
        self,
        fire_at: datetime,
        *,
        state: str,
        ignore_presence: bool,
    ) -> None:
        """Schedule a one-shot alarm callback."""
        from homeassistant.helpers.event import async_track_point_in_time

        self._next_fire = fire_at
        self._state = state

        _LOGGER.info(
            "Wakeup alarm %s scheduled: state=%s utc=%s ignore_presence=%s",
            self.entity_id,
            state,
            self._next_fire,
            ignore_presence,
        )

        async def _cb(_now: datetime) -> None:
            _LOGGER.info(
                "Wakeup alarm callback fired for %s at %s", self.entity_id, _now
            )
            await self._start_alarm(ignore_presence=ignore_presence)

        self._unsubscribe = async_track_point_in_time(self.hass, _cb, self._next_fire)

    async def _schedule_snooze(self, duration_minutes: int) -> None:
        """Schedule a one-off snoozed alarm."""
        from homeassistant.util import dt as dt_util

        minutes = max(1, int(duration_minutes))
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

        snooze_at = dt_util.utcnow() + timedelta(minutes=minutes)
        await self._schedule_callback(
            snooze_at,
            state="snoozed",
            ignore_presence=True,
        )

    async def _cancel_active_run(self) -> None:
        """Request cancellation and wait for the active run to stop."""
        self._cancel_requested = True

        run_task = self._run_task
        if run_task and not run_task.done() and run_task is not asyncio.current_task():
            run_task.cancel()
            with suppress(asyncio.CancelledError):
                await run_task

        while self._running and self._run_task is not asyncio.current_task():
            await asyncio.sleep(0.1)

    async def _stop_music_playback(self) -> None:
        """Stop playback on the configured media player."""
        player_entity = self._entry.options.get(CONF_MA_PLAYER_ENTITY)
        if not player_entity:
            return

        try:
            await self.hass.services.async_call(
                MEDIA_PLAYER_DOMAIN,
                "media_stop",
                {"entity_id": player_entity},
                blocking=False,
            )
        except Exception as exc:
            _LOGGER.error(
                "Error stopping playback for %s on %s: %s",
                self.entity_id,
                player_entity,
                exc,
            )

    async def _start_alarm(self, *, ignore_presence: bool = False) -> None:
        """Start an alarm run, cancelling any currently running one first."""
        if self._running:
            _LOGGER.info(
                "Wakeup alarm %s already running, requesting cancel before restart",
                self.entity_id,
            )
            self._cancel_requested = True
            # wait until the current run finishes its cleanup
            while self._running:
                await asyncio.sleep(0.5)

        # clear cancel flag for the new run
        self._cancel_requested = False
        await self._run_alarm(ignore_presence=ignore_presence)

    async def _run_alarm(self, *, ignore_presence: bool = False) -> None:
        """Execute the wakeup sequence, optionally ignoring presence rules."""
        if self._running:
            # Should not normally happen because _start_alarm handles it,
            # but keep this as a safeguard.
            _LOGGER.info(
                "Wakeup alarm %s _run_alarm called while already running; bailing",
                self.entity_id,
            )
            return

        self._running = True
        self._run_task = asyncio.current_task()
        _LOGGER.info(
            "Running wakeup alarm for %s (require_home=%s person_entity=%s ignore_presence=%s)",
            self.entity_id,
            self._require_home,
            self._person_entity,
            ignore_presence,
        )

        try:
            # presence gate (only if not ignored)
            if not ignore_presence and self._require_home and self._person_entity:
                person_state = self.hass.states.get(self._person_entity)
                _LOGGER.debug(
                    "Presence check for %s: state=%s",
                    self._person_entity,
                    person_state.state if person_state else None,
                )
                if not person_state or person_state.state != "home":
                    _LOGGER.info(
                        "Skipping wakeup alarm for %s because %s is not home",
                        self.entity_id,
                        self._person_entity,
                    )
                    self._state = "skipped"
                    self.async_write_ha_state()
                    await self._reschedule()
                    self.async_write_ha_state()
                    return

            self._state = "triggered"
            self.async_write_ha_state()
            _LOGGER.info("Wakeup alarm TRIGGERED for %s", self.entity_id)

            # run light + music fades in parallel
            try:
                await asyncio.gather(
                    self._fade_light(),
                    self._fade_music(),
                )
            except Exception as exc:
                _LOGGER.error(
                    "Error during alarm sequence for %s: %s", self.entity_id, exc
                )

            await self._reschedule()
            self.async_write_ha_state()

        finally:
            self._running = False
            self._run_task = None
            self.async_write_ha_state()

    async def _fade_light(self) -> None:
        """Fade the configured light up over fade_duration."""
        light_entity = self._entry.options.get(CONF_LIGHT_ENTITY)
        if not light_entity:
            _LOGGER.warning(
                "No light_entity configured in options for %s; skipping light fade",
                self.entity_id,
            )
            return

        duration = max(1, int(self._config.fade_duration))  # seconds
        step_seconds = 5
        steps = max(1, duration // step_seconds)

        _LOGGER.info(
            "Starting manual light fade for %s over %s seconds in %s steps",
            light_entity,
            duration,
            steps,
        )

        for step in range(1, steps + 1):
            if self._cancel_requested:
                _LOGGER.info(
                    "Light fade for %s cancelled at step %s/%s",
                    light_entity,
                    step,
                    steps,
                )
                return

            brightness = int(255 * step / steps)
            _LOGGER.debug(
                "Light fade step %s/%s for %s: brightness=%s",
                step,
                steps,
                light_entity,
                brightness,
            )

            await self.hass.services.async_call(
                LIGHT_DOMAIN,
                "turn_on",
                {
                    "entity_id": light_entity,
                    "brightness": brightness,
                },
                blocking=False,
            )

            if step < steps:
                try:
                    await asyncio.sleep(step_seconds)
                except asyncio.CancelledError:
                    _LOGGER.info(
                        "Light fade for %s cancelled during sleep at step %s/%s",
                        light_entity,
                        step,
                        steps,
                    )
                    return

        _LOGGER.info(
            "Manual light fade complete for %s (brightness=255)", light_entity
        )

    async def _fade_music(self) -> None:
        """Fade music volume around the end of the light fade.

        Music fade duration is self._config.fade_music_duration.
        It starts half that time BEFORE the light reaches 100%,
        and ends half that time AFTER the light reaches 100%.
        """
        player_entity = self._entry.options.get(CONF_MA_PLAYER_ENTITY)
        if not player_entity:
            _LOGGER.warning(
                "No ma_player_entity configured for %s; skipping music fade",
                self.entity_id,
            )
            return

        # Light fade duration (seconds)
        light_duration = max(1, int(self._config.fade_duration))

        # Music fade duration (seconds) - separate from light
        music_duration = int(self._config.fade_music_duration or 0)
        if music_duration <= 0:
            # fall back to light duration if not set
            music_duration = light_duration

        # music fade is centered on the light's end:
        #   start = light_duration - music_duration/2
        #   end   = start + music_duration
        # clamp start to >= 0
        initial_delay = max(0.0, light_duration - music_duration / 2.0)

        # Step resolution
        step_seconds = 5
        steps = max(1, music_duration // step_seconds)

        target_volume = float(self._config.volume or 0.0)
        target_volume = max(0.0, min(target_volume, 1.0))

        _LOGGER.info(
            "Preparing music fade for %s: light_duration=%s, music_duration=%s, "
            "initial_delay=%.1f, steps=%s, target_volume=%.2f",
            player_entity,
            light_duration,
            music_duration,
            initial_delay,
            steps,
            target_volume,
        )

        # Wait until it's time to start fading (unless cancelled)
        waited = 0.0
        while waited < initial_delay:
            if self._cancel_requested:
                _LOGGER.info(
                    "Music fade for %s cancelled during initial delay at %.1fs/%.1fs",
                    player_entity,
                    waited,
                    initial_delay,
                )
                return
            sleep_chunk = min(step_seconds, initial_delay - waited)
            try:
                await asyncio.sleep(sleep_chunk)
            except asyncio.CancelledError:
                _LOGGER.info(
                    "Music fade for %s cancelled during sleep before start",
                    player_entity,
                )
                return
            waited += sleep_chunk

        # At this point, we're 'music_duration/2' seconds before light max.
        # Start playback at volume 0 and begin ramp.
        if self._cancel_requested:
            _LOGGER.info(
                "Music fade for %s cancelled just before start", player_entity
            )
            return

        _LOGGER.info(
            "Starting music fade for %s over %s seconds in %s steps (target_volume=%.2f)",
            player_entity,
            music_duration,
            steps,
            target_volume,
        )

        # Set initial volume to 0
        try:
            await self.hass.services.async_call(
                MEDIA_PLAYER_DOMAIN,
                "volume_set",
                {"entity_id": player_entity, "volume_level": 0.0},
                blocking=False,
            )
        except Exception as exc:
            _LOGGER.error(
                "Error setting initial volume for %s: %s", player_entity, exc
            )

        # Start playback via Music Assistant
        await self._start_music_playback()

        # Ramp volume from 0 -> target_volume over music_duration
        for step in range(1, steps + 1):
            if self._cancel_requested:
                _LOGGER.info(
                    "Music fade for %s cancelled at step %s/%s",
                    player_entity,
                    step,
                    steps,
                )
                return

            volume = target_volume * (step / steps)
            _LOGGER.debug(
                "Music fade step %s/%s for %s: volume=%.3f",
                step,
                steps,
                player_entity,
                volume,
            )

            try:
                await self.hass.services.async_call(
                    MEDIA_PLAYER_DOMAIN,
                    "volume_set",
                    {"entity_id": player_entity, "volume_level": volume},
                    blocking=False,
                )
            except Exception as exc:
                _LOGGER.error(
                    "Error setting volume for %s at step %s/%s: %s",
                    player_entity,
                    step,
                    steps,
                    exc,
                )

            if step < steps:
                try:
                    await asyncio.sleep(step_seconds)
                except asyncio.CancelledError:
                    _LOGGER.info(
                        "Music fade for %s cancelled during sleep at step %s/%s",
                        player_entity,
                        step,
                        steps,
                    )
                    return

        _LOGGER.info(
            "Music fade complete for %s (volume=%.2f)", player_entity, target_volume
        )


    async def _start_music_playback(self) -> None:
        """Start playback via Music Assistant without handling volume."""
        player_entity = self._entry.options.get(CONF_MA_PLAYER_ENTITY)
        playlist_uri = self._config.playlist

        if not player_entity:
            _LOGGER.warning(
                "No ma_player_entity configured in options for %s; skipping music",
                self.entity_id,
            )
            return
        if not playlist_uri:
            _LOGGER.warning(
                "No playlist configured for %s; skipping music playback",
                self.entity_id,
            )
            return

        _LOGGER.info(
            "Starting playlist %r on %s for %s",
            playlist_uri,
            player_entity,
            self.entity_id,
        )

        try:
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
        except Exception as exc:
            _LOGGER.error(
                "Error calling music_assistant.play_media for %s: %s",
                self.entity_id,
                exc,
            )



    async def async_trigger(self) -> None:
        """Manually trigger the alarm (service call)."""
        _LOGGER.info("Manual trigger of wakeup alarm for %s", self.entity_id)
        # manual triggers ignore presence
        await self._start_alarm(ignore_presence=True)

    async def async_snooze(
        self, duration_minutes: int = DEFAULT_SNOOZE_MINUTES
    ) -> None:
        """Cancel the current run and schedule a short one-off retry."""
        if not self._running and self._state not in {"triggered", "snoozed"}:
            _LOGGER.info(
                "Ignoring snooze for %s because no active alarm is present",
                self.entity_id,
            )
            return

        _LOGGER.info(
            "Snoozing wakeup alarm for %s by %s minute(s)",
            self.entity_id,
            duration_minutes,
        )

        await self._cancel_active_run()
        await self._stop_music_playback()
        await self._schedule_snooze(duration_minutes)
        self.async_write_ha_state()

    async def async_stop(self) -> None:
        """Stop the current run or cancel a pending snooze."""
        _LOGGER.info("Stopping wakeup alarm for %s", self.entity_id)

        await self._cancel_active_run()
        await self._stop_music_playback()
        await self._reschedule()
        self.async_write_ha_state()
