// wakeup-alarm-card.js
// Custom Lovelace card for a wakeup_alarm entity.
// Backend contract (from the integration):
// Attributes:
//   enabled (bool)
//   time_of_day (string "HH:MM[:SS]" or ISO datetime)
//   fade_duration (int, seconds)
//   volume (float 0–1)
//   playlist (string)
//   next_fire (ISO string or null)
//   playlist_options (optional string[])
//   device_tracker_entity (optional string)
//   require_home (bool)
// Services:
//   wakeup_alarm.set_config(entity_id, [enabled], [time_of_day],
//                           [fade_duration], [volume], [playlist],
//                           [device_tracker_entity], [require_home])
//   wakeup_alarm.trigger_now(entity_id)  (optional)

import { LitElement, html, css } from "lit";

class WakeupAlarmCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _config: { type: Object },
    };
  }

  static get styles() {
    return css`
      ha-card {
        padding: 16px;
        box-sizing: border-box;
      }

      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
      }

      .title {
        font-size: 1.1rem;
        font-weight: 600;
      }

      .state-pill {
        font-size: 0.8rem;
        padding: 2px 8px;
        border-radius: 999px;
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }

      .grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px 16px;
      }

      .row {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .row.horizontal {
        flex-direction: row;
        justify-content: space-between;
        align-items: center;
      }

      .label {
        font-size: 0.85rem;
        color: var(--secondary-text-color);
      }

      .value {
        font-size: 0.9rem;
        font-weight: 500;
      }

      .footer {
        margin-top: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.8rem;
        color: var(--secondary-text-color);
      }

      .time-input {
        width: 100%;
        box-sizing: border-box;
      }

      select,
      input[type="time"] {
        padding: 4px 6px;
        font-size: 0.9rem;
        border-radius: 4px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        color: var(--primary-text-color);
      }

      ha-slider {
        width: 100%;
      }

      .chips {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }

      .chip {
        padding: 2px 8px;
        border-radius: 999px;
        border: 1px solid var(--divider-color);
        font-size: 0.75rem;
      }

      .small {
        font-size: 0.75rem;
      }
    `;
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You must define an entity");
    }
    this._config = config;
  }

  getCardSize() {
    return 4;
  }

  render() {
    if (!this._config || !this.hass) {
      return html``;
    }

    const entityId = this._config.entity;
    const stateObj = this.hass.states[entityId];

    if (!stateObj) {
      return html`
        <ha-card>
          <div class="header">
            <div class="title">Wakeup Alarm</div>
          </div>
          <div>Entity ${entityId} not found.</div>
        </ha-card>
      `;
    }

    const attrs = stateObj.attributes;
    const enabled = !!attrs.enabled;
    const timeOfDay = this._normalizeTime(attrs.time_of_day);
    const fadeDuration = Number(attrs.fade_duration ?? 900);
    const volume = Number(attrs.volume ?? 0.25);
    const playlist = attrs.playlist ?? "";
    const playlistOptions = attrs.playlist_options || [];
    const nextFire = attrs.next_fire || null;

    const requireHome = Boolean(attrs.require_home);
    const deviceTracker = attrs.device_tracker_entity || null;

    return html`
      <ha-card>
        <div class="header">
          <div class="title">
            ${this._config.name ||
            stateObj.attributes.friendly_name ||
            "Wakeup Alarm"}
          </div>
          <div class="state-pill">
            ${stateObj.state}
          </div>
        </div>

        <div class="grid">
          <!-- Enabled switch -->
          <div class="row horizontal">
            <span class="label">Enabled</span>
            <ha-switch
              .checked=${enabled}
              @change=${(e) => this._updateConfig({ enabled: e.target.checked })}
            ></ha-switch>
          </div>

          <!-- Require home -->
          <div class="row horizontal">
            <span class="label">Require home</span>
            <ha-switch
              .checked=${requireHome}
              @change=${(e) =>
                this._updateConfig({ require_home: e.target.checked })}
            ></ha-switch>
          </div>

          <!-- Time of day -->
          <div class="row">
            <span class="label">Alarm time</span>
            <input
              class="time-input"
              type="time"
              .value=${timeOfDay}
              @change=${(e) => this._updateConfig({ time_of_day: e.target.value })}
            />
          </div>

          <!-- Fade duration -->
          <div class="row">
            <span class="label">Fade duration (min)</span>
            <ha-slider
              min="1"
              max="45"
              step="1"
              .value=${Math.round(fadeDuration / 60)}
              @change=${(e) =>
                this._updateConfig({ fade_duration: Number(e.target.value) * 60 })}
            ></ha-slider>
            <span class="value">${Math.round(fadeDuration / 60)} min</span>
          </div>

          <!-- Volume -->
          <div class="row">
            <span class="label">Volume</span>
            <ha-slider
              min="0"
              max="1"
              step="0.05"
              .value=${volume}
              @change=${(e) =>
                this._updateConfig({ volume: Number(e.target.value) })}
            ></ha-slider>
            <span class="value">${Math.round(volume * 100)}%</span>
          </div>

          <!-- Playlist selector (optional) -->
          <div class="row">
            <span class="label">Playlist</span>
            ${playlistOptions.length
              ? html`
                  <select
                    @change=${(e) =>
                      this._updateConfig({ playlist: e.target.value })}
                  >
                    ${playlistOptions.map(
                      (opt) => html`
                        <option
                          .value=${opt}
                          ?selected=${opt === playlist}
                        >
                          ${opt}
                        </option>
                      `
                    )}
                  </select>
                `
              : html`
                  <span class="value">${playlist || "Default"}</span>
                `}
          </div>
        </div>

        <div class="footer">
          <div>
            Next alarm:<br />
            <span class="value">
              ${nextFire ? this._formatNextFire(nextFire) : "Not scheduled"}
            </span>
            ${deviceTracker
              ? html`<div class="small">
                  Device: ${deviceTracker}
                </div>`
              : html``}
          </div>
          <div class="chips">
            <div
              class="chip"
              @click=${() => this._triggerNow()}
              style="cursor: pointer;"
            >
              Trigger now
            </div>
          </div>
        </div>
      </ha-card>
    `;
  }

  _normalizeTime(value) {
    // Accept "HH:MM", "HH:MM:SS" or full ISO, return "HH:MM"
    if (!value) return "07:00";

    try {
      if (value.length === 5 && value.includes(":")) {
        return value;
      }
      if (value.length >= 8 && value.includes(":") && value.indexOf(":") === 2) {
        // "HH:MM:SS"
        return value.slice(0, 5);
      }
      // ISO datetime
      const date = new Date(value);
      if (!Number.isNaN(date.getTime())) {
        const hh = String(date.getHours()).padStart(2, "0");
        const mm = String(date.getMinutes()).padStart(2, "0");
        return `${hh}:${mm}`;
      }
    } catch {
      // ignore and fall through
    }
    return "07:00";
  }

  _formatNextFire(value) {
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return value;
      return d.toLocaleString();
    } catch {
      return value;
    }
  }

  _updateConfig(partial) {
    const entityId = this._config.entity;
    const [domain] = entityId.split(".");

    this.hass.callService(domain, "set_config", {
      entity_id: entityId,
      ...partial,
    });
  }

  _triggerNow() {
    const entityId = this._config.entity;
    const [domain] = entityId.split(".");

    // Optional service on backend: wakeup_alarm.trigger_now
    this.hass.callService(domain, "trigger_now", {
      entity_id: entityId,
    });
  }
}

customElements.define("wakeup-alarm-card", WakeupAlarmCard);

// Register in the custom card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "wakeup-alarm-card",
  name: "Wakeup Alarm Card",
  description:
    "Control a custom wakeup_alarm entity (time, fade, volume, playlist, require_home).",
});
