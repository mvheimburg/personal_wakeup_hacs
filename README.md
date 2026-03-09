# Personal Wakeup (Home Assistant Integration)

Personal Wakeup is a custom Home Assistant integration that schedules a daily wakeup routine with:
- light fade-in
- Music Assistant playback with volume fade
- optional presence check (`person.*` must be `home`)

## Installation (HACS)
1. Add this repository as a custom repository in HACS (`Integration` type).
2. Install `Personal Wakeup`.
3. Restart Home Assistant.
4. Add the integration from **Settings -> Devices & Services**.

## Configuration
The config flow asks for:
- `light_entity`
- `ma_player_entity`
- optional `person_entity`
- `require_home`
- optional `playlist_options` (comma-separated)

## Services
Domain: `personal_wakeup`
- `set_config`
: Update runtime alarm settings (`entity_id`, `enabled`, `time_of_day`, `fade_duration`, `volume`, `playlist`, `require_home`).
- `trigger_now`
: Trigger alarm immediately (`entity_id`).
- `snooze`
: Stop the current run and trigger it again after `duration_minutes` (defaults to 10).
- `stop`
: Stop the current run and cancel any active snooze.

## Notes
- Integration entities are created on the `sensor` platform.
- For UI control, pair this integration with the `lovelace-personal-wakeup-card` repo.
