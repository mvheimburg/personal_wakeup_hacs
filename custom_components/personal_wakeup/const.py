"""Constants for the Personal Wakeup integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "personal_wakeup"

CONF_LIGHT_ENTITY = "light_entity"
CONF_MA_PLAYER_ENTITY = "ma_player_entity"
CONF_PERSON_ENTITY = "person_entity"
CONF_REQUIRE_HOME = "require_home"
CONF_PLAYLIST_OPTIONS = "playlist_options"

DATA_CONFIG_ENTRIES = "config_entries"
DATA_ALARM_ENTITIES = "alarm_entities"
DATA_SERVICES_REGISTERED = "services_registered"

SERVICE_SET_CONFIG = "set_config"
SERVICE_TRIGGER_NOW = "trigger_now"
SERVICE_SNOOZE = "snooze"
SERVICE_STOP = "stop"

DEFAULT_SNOOZE_MINUTES = 10

PLATFORMS: list[Platform] = [Platform.SENSOR]
