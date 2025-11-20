"""Constants for the Personal Wakeup integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "personal_wakeup"

CONF_LIGHT_ENTITY = "light_entity"
CONF_MA_PLAYER_ENTITY = "ma_player_entity"
CONF_PERSON_ENTITY = "person_entity"
CONF_REQUIRE_HOME = "require_home"
CONF_PLAYLIST_OPTIONS = "playlist_options"

PLATFORMS: list[Platform] = [Platform.SENSOR]