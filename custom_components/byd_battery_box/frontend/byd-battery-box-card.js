/*
 * BYD Battery-Box card for Home Assistant
 * Shipped with the byd_battery_box integration – no separate installation needed.
 * https://github.com/plumsl/byd_battery_box
 */
const CARD_VERSION = "0.3.0-beta.3";
const DOMAIN = "byd_battery_box";
const CARD_TYPE = "byd-battery-box-card";

const DEFAULT_COLORS = {
  low: "#378ADD",
  mid: "#5DCAA5",
  high: "#EF9F27",
  balancing: "#E24B4A",
  cold: "#378ADD",
  normal: "#E3E1D9",
  warm: "#D85A30",
};
// Temperature scale: cold at/below TEMP_COLD, neutral at TEMP_NORMAL, warm at/above TEMP_WARM
const TEMP_COLD = 10, TEMP_NORMAL = 25, TEMP_WARM = 40;
const DEFAULTS = {
  title: "",
  scale_mv: 15,
  swap_modules: false,
  show_header: true,
  show_balancing_cells: false,
};
const SERIES = ["#7F77DD", "#1D9E75", "#D85A30", "#D4537E", "#378ADD", "#BA7517"];

const I18N = {
  en: {
    title: "BYD Battery-Box", live: "Live", history: "History", soc: "State of charge",
    power: "Power", soh: "Health", remaining: "Remaining", status: "Status", normal: "Normal",
    warnings: "warnings", warning: "warning", charging: "charging", discharging: "discharging",
    idle: "idle", spread: "Spread", cells: "Cells", module: "Module", cell: "Cell",
    sensor: "Sensor", balancing: "Balancing", legend_low: "below average",
    legend_high: "above average", soh_title: "State of health (daily mean)",
    spread_title: "Cell spread per BMS (daily maximum)",
    heat_title: "Cell deviation from BMS average (daily mean, 30 days)",
    soc_title: "State of charge per BMS (daily mean, 30 days)",
    no_data: "Not enough long-term data yet – statistics are collected from installation onwards.",
    loading: "Loading statistics…", not_found: "No BYD Battery-Box entities found.",
    unavailable: "unavailable", cycles: "Full cycles",
    capacity: "Capacity", share: "Share", weakest: "weakest cell", ri: "Ri",
    cap_title: "Relative capacity per BMS (100 % = average, daily mean)",
    ri_title: "Internal resistance per BMS (experimental, daily mean)",
    share_title: "Current share per BMS (daily mean)",
  },
  de: {
    title: "BYD Battery-Box", live: "Live", history: "Verlauf", soc: "Ladezustand",
    power: "Leistung", soh: "Gesundheit", remaining: "Restenergie", status: "Status",
    normal: "Normal", warnings: "Warnungen", warning: "Warnung", charging: "lädt",
    discharging: "entlädt", idle: "Ruhe", spread: "Spreizung", cells: "Zellen",
    module: "Modul", cell: "Zelle", sensor: "Fühler", balancing: "Balancing",
    legend_low: "unter Mittelwert", legend_high: "über Mittelwert",
    soh_title: "Gesundheitszustand (Tagesmittel)",
    spread_title: "Zellspreizung je BMS (Tagesmaximum)",
    heat_title: "Zellabweichung vom BMS-Mittel (Tagesmittel, 30 Tage)",
    soc_title: "Ladezustand je BMS (Tagesmittel, 30 Tage)",
    no_data: "Noch zu wenig Langzeitdaten – die Statistik wird ab der Installation gesammelt.",
    loading: "Lade Statistik…", not_found: "Keine Entitäten der BYD Battery-Box gefunden.",
    unavailable: "nicht verfügbar", cycles: "Vollzyklen",
    capacity: "Kapazität", share: "Anteil", weakest: "auffälligste Zelle", ri: "Ri",
    cap_title: "Relative Kapazität je BMS (100 % = Durchschnitt, Tagesmittel)",
    ri_title: "Innenwiderstand je BMS (experimentell, Tagesmittel)",
    share_title: "Stromanteil je BMS (Tagesmittel)",
  },
};

/* ---------- helpers ---------- */
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function rgb(hex) {
  let h = String(hex || "#888888").replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h.slice(0, 6), 16) || 0;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function mix(a, b, t) {
  const A = rgb(a), B = rgb(b);
  return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, "0")).join("");
}
const textOn = (hex) => { const [r, g, b] = rgb(hex); return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#1c1c1c" : "#ffffff"; };
const devColor = (d, scale, c) => { const x = Math.max(-1, Math.min(1, d / scale)); return x >= 0 ? mix(c.mid, c.high, x) : mix(c.mid, c.low, -x); };
const tempColor = (v, c) => v >= TEMP_NORMAL
  ? mix(c.normal, c.warm, Math.min(1, (v - TEMP_NORMAL) / (TEMP_WARM - TEMP_NORMAL)))
  : mix(c.normal, c.cold, Math.min(1, (TEMP_NORMAL - v) / (TEMP_NORMAL - TEMP_COLD)));
const num = (hass, id) => { const s = id && hass.states[id]; if (!s) return null; const v = parseFloat(s.state); return Number.isFinite(v) ? v : null; };
const fmt = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: false }));
const startMs = (p) => (typeof p.start === "number" ? p.start : Date.parse(p.start));

/* ---------- entity discovery ---------- */
function discover(hass, wantedDevice) {
  const entries = Object.values(hass.entities || {}).filter((e) => e.platform === DOMAIN);
  const byDevice = {};
  for (const e of entries) {
    const dev = e.device_id || "_";
    const d = (byDevice[dev] ||= { keys: {}, cells: [], temps: [], bms: null, alarms: [] });
    const st = hass.states[e.entity_id];
    const a = (st && st.attributes) || {};
    if (e.translation_key === "cell_voltage" && a.cell) { d.cells[a.cell - 1] = e.entity_id; d.bms = a.bms; }
    else if (e.translation_key === "cell_temperature" && a.sensor) { d.temps[a.sensor - 1] = e.entity_id; d.bms = a.bms; }
    else if (e.entity_id.startsWith("binary_sensor.")) d.alarms.push(e.entity_id);
    else if (e.translation_key) d.keys[e.translation_key] = e.entity_id;
  }
  const devices = hass.devices || {};
  const bmus = Object.keys(byDevice).filter((id) => byDevice[id].bms == null && byDevice[id].keys.soc);
  const bmu = wantedDevice && bmus.includes(wantedDevice) ? wantedDevice : bmus[0];
  if (!bmu) return null;
  const bms = Object.keys(byDevice)
    .filter((id) => byDevice[id].bms != null && (bmus.length === 1 || (devices[id] && devices[id].via_device_id === bmu)))
    .map((id) => ({ device_id: id, index: byDevice[id].bms, ...byDevice[id] }))
    .sort((a, b) => a.index - b.index);
  return { bmu: { device_id: bmu, ...byDevice[bmu] }, bms };
}

/* ---------- styles ---------- */
const STYLE = `
:host{display:block}
ha-card{display:block;padding:16px;overflow:hidden}
.top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:12px}
.ttl{font-size:18px;font-weight:500;color:var(--primary-text-color)}
.tabs{display:flex;gap:4px;background:var(--secondary-background-color);border-radius:8px;padding:3px}
.tab{border:0;background:none;color:var(--secondary-text-color);font:inherit;font-size:13px;padding:4px 12px;border-radius:6px;cursor:pointer}
.tab.on{background:var(--card-background-color);color:var(--primary-text-color)}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-bottom:12px}
.m{background:var(--secondary-background-color);border-radius:8px;padding:8px 10px;cursor:pointer}
.ml{font-size:12px;color:var(--secondary-text-color)}
.mv{font-size:20px;font-weight:500;color:var(--primary-text-color);white-space:nowrap}
.ms{font-size:12px;color:var(--secondary-text-color)}
.towers{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.tw{border:1px solid var(--divider-color);border-radius:12px;padding:10px}
.th{display:flex;justify-content:space-between;align-items:baseline;cursor:pointer}
.tn{font-weight:500;color:var(--primary-text-color)}
.lbl{font-size:12px;color:var(--secondary-text-color)}
.bar{height:6px;border-radius:3px;background:var(--secondary-background-color);margin:6px 0 3px;overflow:hidden}
.bar>div{height:100%;border-radius:3px;background:var(--success-color,#43a047)}
.mod{border:1px solid var(--divider-color);border-radius:8px;padding:10px 4px 4px;margin-top:10px;position:relative}
.mt{position:absolute;top:-9px;left:8px;background:var(--card-background-color);padding:0 4px;font-size:11px;color:var(--secondary-text-color)}
.cells{display:grid;grid-template-columns:repeat(8,1fr);gap:2px}
.cell{position:relative;height:74px;border-radius:3px;display:flex;align-items:center;justify-content:center;font-size:11px;cursor:pointer;box-sizing:border-box}
.cell span{writing-mode:vertical-rl;transform:rotate(180deg)}
.weak::after{content:"";position:absolute;top:3px;left:50%;transform:translateX(-50%);border:5px solid transparent;border-top-color:currentColor}
.health{font-size:12px;color:var(--secondary-text-color);margin-top:2px}
.temps{display:grid;grid-template-columns:repeat(4,1fr);margin-top:4px;justify-items:center}
.tp{font-size:11px;padding:1px 6px;border-radius:9px;cursor:pointer}
.alert{color:var(--error-color,#db4437)}
.legend{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:12px;color:var(--secondary-text-color);flex-wrap:wrap}
.grad{width:140px;height:8px;border-radius:4px}
.hint{font-size:12px;color:var(--secondary-text-color);min-height:16px;margin-top:6px}
.sec{margin:6px 0 18px}
.sec h3{font-size:14px;font-weight:500;margin:0 0 6px;color:var(--primary-text-color)}
.lg{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--secondary-text-color);margin-top:4px}
.dot{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.heat{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
svg text{fill:var(--secondary-text-color);font-size:11px}
`;

/* ---------- card ---------- */
class BydBatteryBoxCard extends HTMLElement {
  static getConfigElement() { return document.createElement(`${CARD_TYPE}-editor`); }
  static getStubConfig() { return {}; }

  setConfig(config) {
    this._config = { ...DEFAULTS, ...config, colors: { ...DEFAULT_COLORS, ...(config.colors || {}) } };
    this._view = this._view || "live";
    this._sig = null;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (hass.entities !== this._entitiesRef) { this._entitiesRef = hass.entities; this._model = null; }
    if (this._view === "live") this._render();
  }

  getCardSize() { return 10; }
  getGridOptions() { return { columns: "full", min_columns: 6 }; }

  _t(k) { const l = (this._hass && this._hass.language || "en").startsWith("de") ? "de" : "en"; return I18N[l][k] || I18N.en[k] || k; }

  _ensureRoot() {
    if (this._root) return;
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div id="c"></div><div class="hint" id="hint"></div></ha-card>`;
    this._root = this.shadowRoot.getElementById("c");
    this._hint = this.shadowRoot.getElementById("hint");
    this._root.addEventListener("click", (ev) => {
      const tab = ev.target.closest("[data-view]");
      if (tab) { this._view = tab.dataset.view; this._sig = null; this._render(); return; }
      const el = ev.target.closest("[data-entity]");
      if (el) this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: el.dataset.entity } }));
    });
    this._root.addEventListener("mouseover", (ev) => { const el = ev.target.closest("[data-tip]"); this._hint.textContent = el ? el.dataset.tip : ""; });
    this._root.addEventListener("mouseleave", () => { this._hint.textContent = ""; });
  }

  _render() {
    if (!this._config || !this._hass) return;
    this._ensureRoot();
    if (!this._model) this._model = discover(this._hass, this._config.device_id);
    const m = this._model;
    if (!m) { this._root.innerHTML = `<div class="lbl">${this._t("not_found")}</div>`; return; }
    if (this._view === "history") { this._renderHistory(m); return; }

    const ids = [...Object.values(m.bmu.keys), ...m.bmu.alarms];
    m.bms.forEach((b) => ids.push(...Object.values(b.keys), ...b.cells, ...b.temps, ...b.alarms));
    const sig = ids.map((id) => { const s = this._hass.states[id]; return s ? s.state + (s.attributes.cells_experimental || "") : ""; }).join("|");
    if (sig === this._sig) return;
    this._sig = sig;
    this._root.innerHTML = this._header() + this._metrics(m) + `<div class="towers">${m.bms.map((b) => this._tower(b)).join("")}</div>` + this._legend();
  }

  _header() {
    if (!this._config.show_header) return "";
    const tab = (v) => `<button class="tab ${this._view === v ? "on" : ""}" data-view="${v}">${this._t(v)}</button>`;
    return `<div class="top"><div class="ttl">${esc(this._config.title || this._t("title"))}</div><div class="tabs">${tab("live")}${tab("history")}</div></div>`;
  }

  _metrics(m) {
    const h = this._hass, k = m.bmu.keys;
    const p = num(h, k.power);
    const dir = p == null ? "" : p > 20 ? this._t("discharging") : p < -20 ? this._t("charging") : this._t("idle");
    const alarms = [...m.bmu.alarms, ...m.bms.flatMap((b) => b.alarms)].filter((id) => h.states[id] && h.states[id].state === "on");
    const statusVal = alarms.length ? `<span class="alert">${alarms.length} ${this._t(alarms.length === 1 ? "warning" : "warnings")}</span>`
      : (h.states[k.status] && h.states[k.status].state !== "unavailable" ? this._t("normal") : this._t("unavailable"));
    const box = (label, value, sub, ent) => `<div class="m" data-entity="${ent || ""}"><div class="ml">${label}</div><div class="mv">${value}</div><div class="ms">${sub || "&nbsp;"}</div></div>`;
    return `<div class="metrics">
      ${box(this._t("soc"), `${fmt(num(h, k.soc))} %`, "", k.soc)}
      ${box(this._t("power"), `${fmt(p == null ? null : Math.abs(p))} W`, dir, k.power)}
      ${box(this._t("soh"), `${fmt(num(h, k.soh))} %`, `${fmt(num(h, k.full_cycles))} ${this._t("cycles")}`, k.soh)}
      ${box(this._t("remaining"), `${fmt(num(h, k.remaining_energy), 1)} kWh`, `/ ${fmt(num(h, k.usable_capacity), 1)} kWh`, k.remaining_energy)}
      ${box(this._t("status"), statusVal, "", alarms[0] || k.status)}</div>`;
  }

  _tower(b) {
    const h = this._hass, c = this._config.colors, k = b.keys;
    const volts = b.cells.map((id) => num(h, id));
    const valid = volts.filter((v) => v != null);
    const avg = valid.length ? valid.reduce((s, v) => s + v, 0) / valid.length : 0;
    const soc = num(h, k.soc), cur = num(h, k.current);
    const balSt = h.states[k.balancing];
    const balCells = (this._config.show_balancing_cells && balSt && balSt.attributes.cells_experimental) || [];
    const alarmOn = b.alarms.some((id) => h.states[id] && h.states[id].state === "on");
    const weak = num(h, k.weakest_cell);
    const mod = (from, name) => {
      let cells = "";
      for (let i = from; i < from + 8; i++) {
        const v = volts[i], id = b.cells[i];
        const bg = v == null ? "var(--disabled-color,#bdbdbd)" : devColor(v - avg, this._config.scale_mv, c);
        const bal = balCells.includes(i + 1);
        const isWeak = weak === i + 1;
        const tip = `BMS ${b.index} · ${this._t("cell")} ${i + 1}: ${fmt(v)} mV (${v - avg >= 0 ? "+" : ""}${fmt(v - avg)} mV)${bal ? " · " + this._t("balancing") : ""}${isWeak ? " · " + this._t("weakest") : ""}`;
        cells += `<div class="cell${isWeak ? " weak" : ""}" data-entity="${id || ""}" data-tip="${esc(tip)}" style="background:${bg};color:${textOn(bg.startsWith("#") ? bg : "#bdbdbd")};${bal ? `box-shadow:inset 0 0 0 2px ${c.balancing}` : ""}"><span>${fmt(v)}</span></div>`;
      }
      const t0 = from === 0 ? 0 : 4;
      let temps = "";
      for (let j = t0; j < t0 + 4; j++) {
        const v = num(h, b.temps[j]);
        const bg = v == null ? "#bdbdbd" : tempColor(v, c);
        temps += `<span class="tp" data-entity="${b.temps[j] || ""}" data-tip="BMS ${b.index} · ${this._t("sensor")} T${j + 1}: ${fmt(v)} °C" style="background:${bg};color:${textOn(bg)}">${fmt(v)}°</span>`;
      }
      return `<div class="mod"><div class="mt">${name}</div><div class="cells">${cells}</div><div class="temps">${temps}</div></div>`;
    };
    const upper = mod(8, `${this._t("module")} B2 · ${this._t("cells")} 9–16`);
    const lower = mod(0, `${this._t("module")} B1 · ${this._t("cells")} 1–8`);
    return `<div class="tw">
      <div class="th" data-entity="${k.soc || ""}"><span class="tn">${alarmOn ? '<span class="alert">⚠ </span>' : ""}BMS ${b.index}</span><span class="lbl">${fmt(soc, 1)} % · ${fmt(cur, 1)} A</span></div>
      <div class="bar"><div style="width:${Math.max(0, Math.min(100, soc || 0))}%"></div></div>
      <div class="lbl" data-entity="${k.cell_spread || ""}">${this._t("spread")} ${fmt(num(h, k.cell_spread))} mV · ${this._t("balancing")} ${fmt(num(h, k.balancing))}</div>
      ${k.relative_capacity ? `<div class="health" data-entity="${k.relative_capacity}" data-tip="${this._t("capacity")}: ${this._t("cap_title")}">${this._t("capacity")} ${fmt(num(h, k.relative_capacity), 1)} % · ${this._t("share")} ${fmt(num(h, k.current_share), 1)} %${num(h, k.internal_resistance) != null ? ` · ${this._t("ri")} ${fmt(num(h, k.internal_resistance), 1)} mΩ` : ""}</div>` : ""}
      ${this._config.swap_modules ? lower + upper : upper + lower}</div>`;
  }

  _legend() {
    const c = this._config.colors, s = this._config.scale_mv;
    return `<div class="legend"><span>−${s} mV</span><div class="grad" style="background:linear-gradient(90deg,${c.low},${c.mid},${c.high})"></div><span>+${s} mV</span>
      <span style="margin-left:auto">${TEMP_COLD} °C</span><div class="grad" style="width:80px;background:linear-gradient(90deg,${c.cold},${c.normal},${c.warm})"></div><span>${TEMP_WARM} °C</span></div>`;
  }

  /* ---------- history ---------- */
  async _renderHistory(m) {
    this._root.innerHTML = this._header() + `<div class="lbl">${this._t("loading")}</div>`;
    const now = Date.now();
    if (!this._stats || now - this._statsAt > 600000) {
      const ids = new Set([m.bmu.keys.soh]);
      m.bms.forEach((b) => { [b.keys.soh, b.keys.cell_spread, b.keys.soc, b.keys.relative_capacity, b.keys.current_share, b.keys.internal_resistance, ...b.cells].forEach((id) => id && ids.add(id)); });
      try {
        this._stats = await this._hass.callWS({
          type: "recorder/statistics_during_period",
          start_time: new Date(now - 365 * 864e5).toISOString(),
          statistic_ids: [...ids].filter(Boolean),
          period: "day",
          types: ["mean", "max"],
        });
        this._statsAt = now;
      } catch (err) {
        this._root.innerHTML = this._header() + `<div class="lbl">${esc(err.message || err)}</div>`;
        return;
      }
    }
    if (this._view !== "history") return;
    const S = this._stats || {};
    const since30 = now - 30 * 864e5, since90 = now - 90 * 864e5;
    const pts = (id, type, since = 0) => (S[id] || []).map((p) => [startMs(p), p[type]]).filter((p) => p[0] >= since && p[1] != null);
    const series = (key, type, since) => m.bms.map((b, i) => ({ name: `BMS ${b.index}`, color: SERIES[i % SERIES.length], pts: pts(b.keys[key], type, since) }));

    const soh = [{ name: "System", color: "#888780", pts: pts(m.bmu.keys.soh, "mean") }, ...series("soh", "mean", 0)];
    const enough = soh[0].pts.length >= 2;
    let html = this._header();
    if (!enough) html += `<div class="lbl" style="margin-bottom:12px">${this._t("no_data")}</div>`;
    html += `<div class="sec"><h3>${this._t("soh_title")}</h3>${chart(soh, "%", 0)}</div>`;
    html += `<div class="sec"><h3>${this._t("cap_title")}</h3>${chart(series("relative_capacity", "mean", 0), "%", 1)}</div>`;
    html += `<div class="sec"><h3>${this._t("share_title")}</h3>${chart(series("current_share", "mean", since90), "%", 1)}</div>`;
    html += `<div class="sec"><h3>${this._t("ri_title")}</h3>${chart(series("internal_resistance", "mean", since90), "mΩ", 1)}</div>`;
    html += `<div class="sec"><h3>${this._t("spread_title")}</h3>${chart(series("cell_spread", "max", since90), "mV", 0)}</div>`;
    html += `<div class="sec"><h3>${this._t("soc_title")}</h3>${chart(series("soc", "mean", since30), "%", 0)}</div>`;
    html += `<div class="sec"><h3>${this._t("heat_title")}</h3><div class="heat">${m.bms.map((b) => this._heat(b, S, since30)).join("")}</div></div>`;
    this._root.innerHTML = html;
  }

  _heat(b, S, since) {
    const days = new Map();
    b.cells.forEach((id, ci) => (S[id] || []).forEach((p) => {
      const t = startMs(p); if (t < since || p.mean == null) return;
      const day = days.get(t) || []; day[ci] = p.mean; days.set(t, day);
    }));
    const cols = [...days.keys()].sort((a, b2) => a - b2);
    const W = 200, rowH = 9, lw = 26, cw = cols.length ? (W - lw) / cols.length : 0;
    let rects = "";
    cols.forEach((t, x) => {
      const vals = days.get(t), ok = vals.filter((v) => v != null);
      const avg = ok.reduce((s, v) => s + v, 0) / (ok.length || 1);
      for (let r = 0; r < 16; r++) {
        const v = vals[r]; if (v == null) continue;
        const d = v - avg;
        rects += `<rect x="${(lw + x * cw).toFixed(1)}" y="${(15 - r) * rowH}" width="${Math.max(cw - 0.5, 0.5).toFixed(1)}" height="${rowH - 1}" fill="${devColor(d, this._config.scale_mv, this._config.colors)}"><title>${this._t("cell")} ${r + 1} · ${new Date(t).toLocaleDateString()}: ${d >= 0 ? "+" : ""}${d.toFixed(1)} mV</title></rect>`;
      }
    });
    const labels = [16, 9, 8, 1].map((n) => `<text x="0" y="${(16 - n) * rowH + 8}">Z${n}</text>`).join("");
    return `<div><div class="lbl">BMS ${b.index}</div><svg viewBox="0 0 ${W} ${16 * rowH + 2}" width="100%">${labels}<line x1="${lw}" x2="${W}" y1="${8 * rowH - 0.5}" y2="${8 * rowH - 0.5}" stroke="var(--divider-color)"/>${rects}</svg></div>`;
  }
}

/* ---------- tiny SVG line chart ---------- */
function chart(series, unit, digits) {
  const all = series.flatMap((s) => s.pts);
  if (all.length < 2) return `<div class="lbl">–</div>`;
  const W = 600, H = 150, L = 40, R = 8, T = 8, B = 20;
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (x1 === x0) x1 = x0 + 864e5;
  const pad = (y1 - y0) * 0.1 || 1; y0 -= pad; y1 += pad;
  const X = (x) => L + ((x - x0) / (x1 - x0)) * (W - L - R), Y = (y) => T + (1 - (y - y0) / (y1 - y0)) * (H - T - B);
  const lines = series.filter((s) => s.pts.length).map((s) =>
    `<polyline fill="none" stroke="${s.color}" stroke-width="2" points="${s.pts.map((p) => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ")}"/>` +
    (s.pts.length === 1 ? `<circle cx="${X(s.pts[0][0])}" cy="${Y(s.pts[0][1])}" r="3" fill="${s.color}"/>` : "")).join("");
  const grid = [y0 + pad, (y0 + y1) / 2, y1 - pad].map((v) =>
    `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--divider-color)"/><text x="${L - 4}" y="${Y(v) + 4}" text-anchor="end">${fmt(v, digits)}</text>`).join("");
  const d = (t) => new Date(t).toLocaleDateString(undefined, { day: "2-digit", month: "2-digit", year: "2-digit" });
  const axis = `<text x="${L}" y="${H - 4}">${d(x0)}</text><text x="${W - R}" y="${H - 4}" text-anchor="end">${d(x1)}</text><text x="${L - 4}" y="${T + 2}" text-anchor="end">${unit}</text>`;
  const legend = `<div class="lg">${series.map((s) => `<span><span class="dot" style="background:${s.color}"></span>${esc(s.name)}</span>`).join("")}</div>`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%">${grid}${lines}${axis}</svg>${legend}`;
}

/* ---------- editor ---------- */
const EDITOR_FIELDS = [
  ["title", "text", { de: "Titel", en: "Title" }],
  ["scale_mv", "number", { de: "Volle Farbe ab Abweichung (mV)", en: "Full colour at deviation (mV)" }],
  ["swap_modules", "checkbox", { de: "Module oben/unten tauschen", en: "Swap upper/lower module" }],
  ["show_header", "checkbox", { de: "Kopfzeile mit Umschalter anzeigen", en: "Show header with view switch" }],
  ["show_balancing_cells", "checkbox", { de: "Balancierende Zellen markieren (experimentell)", en: "Mark balancing cells (experimental)" }],
];
const COLOR_FIELDS = [
  ["low", { de: "Zelle unter Mittel", en: "Cell below average" }],
  ["mid", { de: "Zelle im Mittel", en: "Cell at average" }],
  ["high", { de: "Zelle über Mittel", en: "Cell above average" }],
  ["balancing", { de: "Balancing-Rahmen", en: "Balancing frame" }],
  ["cold", { de: "Temperatur kalt (10 °C)", en: "Temperature cold (10 °C)" }],
  ["normal", { de: "Temperatur normal (25 °C)", en: "Temperature normal (25 °C)" }],
  ["warm", { de: "Temperatur warm (40 °C)", en: "Temperature warm (40 °C)" }],
];

class BydBatteryBoxCardEditor extends HTMLElement {
  set hass(hass) { this._hass = hass; if (!this._built) this._build(); }
  setConfig(config) { this._config = { ...config }; if (this._built) this._sync(); else if (this._hass) this._build(); }
  _lang() { return (this._hass && this._hass.language || "en").startsWith("de") ? "de" : "en"; }
  _build() {
    if (!this._config) return;
    this._built = true;
    const l = this._lang();
    const row = (inner) => `<label style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin:8px 0">${inner}</label>`;
    let html = "<div style='padding:4px 0'>";
    for (const [key, type, label] of EDITOR_FIELDS)
      html += row(`<span>${label[l]}</span><input data-key="${key}" type="${type}" ${type === "number" ? 'min="2" max="100" step="1" style="width:80px"' : ""} ${type === "text" ? 'style="flex:1;max-width:240px"' : ""}>`);
    html += `<div style="margin-top:14px;font-weight:500">${l === "de" ? "Farben" : "Colours"}</div>`;
    for (const [key, label] of COLOR_FIELDS) html += row(`<span>${label[l]}</span><input data-color="${key}" type="color">`);
    html += `<button id="reset" style="margin-top:8px">${l === "de" ? "Farben zurücksetzen" : "Reset colours"}</button></div>`;
    this.innerHTML = html;
    this.querySelectorAll("input").forEach((el) => el.addEventListener("change", () => this._changed(el)));
    this.querySelector("#reset").addEventListener("click", () => { const c = { ...this._config }; delete c.colors; this._fire(c); });
    this._sync();
  }
  _sync() {
    const cfg = { ...DEFAULTS, ...this._config }, colors = { ...DEFAULT_COLORS, ...(this._config.colors || {}) };
    this.querySelectorAll("input[data-key]").forEach((el) => { const v = cfg[el.dataset.key]; if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? ""; });
    this.querySelectorAll("input[data-color]").forEach((el) => { el.value = colors[el.dataset.color]; });
  }
  _changed(el) {
    const c = { ...this._config };
    if (el.dataset.color) c.colors = { ...(c.colors || {}), [el.dataset.color]: el.value };
    else if (el.type === "checkbox") c[el.dataset.key] = el.checked;
    else if (el.type === "number") c[el.dataset.key] = Math.max(2, Math.min(100, parseInt(el.value, 10) || DEFAULTS.scale_mv));
    else if (el.value) c[el.dataset.key] = el.value; else delete c[el.dataset.key];
    this._fire(c);
  }
  _fire(config) { this._config = config; this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true })); }
}

/* =====================================================================
 * Health assessment (shared by the health card and the compact card)
 * ===================================================================== */
const HEALTH_I18N = {
  en: {
    health_title: "Battery health", soh: "Health (SOH)", cycles: "Full cycles", usable: "Usable capacity",
    last_cycle: "Last cycle", depth: "depth", rel_cap: "Relative capacity", cur_share: "Current share",
    expected: "expected", ri: "Internal resistance", weakest: "Weakest cell", trend: "Capacity trend (90 days)",
    collecting: "collecting data", of: "of", full_charges: "full charges", load_steps: "load steps",
    src_cycles: "from {n} full cycles", src_lifetime: "from lifetime counters",
    ok: "Everything inconspicuous.", cap_avg: "Capacity on average.",
    cap_dev: "Capacity {v} % {dir} average.", below: "below", above: "above",
    share_low: "Takes {v} points less current than its capacity suggests – watch the connection.",
    ri_high: "Internal resistance {v} % above the other modules.",
    cell_dev: "Cell {c} deviates by {v} mV at the end of charge.",
    trend_down: "Capacity is falling ({v} points in 90 days).",
    no_data: "Not enough data yet.", cell: "Cell", alarm: "Alarm active",
    empty_in: "empty in", full_in: "full in", idle: "idle", charging: "charging", discharging: "discharging",
  },
  de: {
    health_title: "Batteriezustand", soh: "Gesundheit (SOH)", cycles: "Vollzyklen", usable: "Nutzbare Kapazität",
    last_cycle: "Letzter Zyklus", depth: "Tiefe", rel_cap: "Relative Kapazität", cur_share: "Stromanteil",
    expected: "erwartet", ri: "Innenwiderstand", weakest: "Auffälligste Zelle", trend: "Kapazitätstrend (90 Tage)",
    collecting: "sammelt Daten", of: "von", full_charges: "Vollladungen", load_steps: "Laständerungen",
    src_cycles: "aus {n} Vollzyklen", src_lifetime: "aus Lebensdauer-Zählern",
    ok: "Alles unauffällig.", cap_avg: "Kapazität im Durchschnitt.",
    cap_dev: "Kapazität {v} % {dir} Durchschnitt.", below: "unter", above: "über",
    share_low: "Nimmt {v} Punkte weniger Strom auf, als die Kapazität erwarten lässt – Anschluss beobachten.",
    ri_high: "Innenwiderstand {v} % über den anderen Modulen.",
    cell_dev: "Zelle {c} weicht am Ladeende um {v} mV ab.",
    trend_down: "Kapazität sinkt ({v} Punkte in 90 Tagen).",
    no_data: "Noch zu wenig Daten.", cell: "Zelle", alarm: "Alarm aktiv",
    empty_in: "leer in", full_in: "voll in", idle: "Ruhe", charging: "lädt", discharging: "entlädt",
  },
};
const ht = (hass, k, vars = {}) => {
  const l = (hass && hass.language || "en").startsWith("de") ? "de" : "en";
  let s = HEALTH_I18N[l][k] || HEALTH_I18N.en[k] || k;
  for (const [n, v] of Object.entries(vars)) s = s.replace(`{${n}}`, v);
  return s;
};
const LEVEL_COLOR = ["var(--success-color,#43a047)", "var(--warning-color,#ffa600)", "var(--error-color,#db4437)"];
const attr = (hass, id, a) => (id && hass.states[id] ? hass.states[id].attributes[a] : undefined);

/* Assess one BMS. trend = change of relative capacity over 90 days (points) or null. */
function assess(hass, m, b, trend = null) {
  const k = b.keys, n = m.bms.length;
  const findings = [];
  let level = 0, data = false;
  const bump = (l) => { level = Math.max(level, l); };
  if (b.alarms.some((id) => hass.states[id] && hass.states[id].state === "on")) { bump(2); findings.push(ht(hass, "alarm")); }

  const cap = num(hass, k.relative_capacity);
  if (cap != null) {
    data = true;
    const d = cap - 100, ad = Math.abs(d);
    bump(ad <= 3 ? 0 : ad <= 6 ? 1 : 2);
    findings.push(ad < 1.5 ? ht(hass, "cap_avg")
      : ht(hass, "cap_dev", { v: fmt(ad, 1), dir: ht(hass, d < 0 ? "below" : "above") }));
  }
  const share = num(hass, k.current_share), samples = attr(hass, k.current_share, "samples") || 0;
  if (share != null && cap != null && samples >= 100) {
    const diff = share - cap / n;
    if (diff <= -2) { bump(diff <= -4 ? 2 : 1); findings.push(ht(hass, "share_low", { v: fmt(-diff, 1) })); }
  }
  const ri = num(hass, k.internal_resistance);
  const others = m.bms.filter((o) => o !== b).map((o) => num(hass, o.keys.internal_resistance)).filter((v) => v != null);
  if (ri != null && others.length) {
    const avg = others.reduce((s, v) => s + v, 0) / others.length;
    const rel = 100 * (ri / avg - 1);
    if (rel > 20) { bump(rel > 50 ? 2 : 1); findings.push(ht(hass, "ri_high", { v: fmt(rel, 0) })); }
  }
  const weak = num(hass, k.weakest_cell), score = attr(hass, k.weakest_cell, "score_mv");
  if (weak != null && score != null && score > 15) {
    bump(score > 30 ? 2 : 1); findings.push(ht(hass, "cell_dev", { c: weak, v: fmt(score, 0) }));
  }
  if (trend != null && trend < -1.5) { bump(trend < -3 ? 2 : 1); findings.push(ht(hass, "trend_down", { v: fmt(trend, 1) })); }

  if (!data) findings.push(ht(hass, "no_data"));
  else if (level === 0 && findings.length === 1 && findings[0] === ht(hass, "cap_avg")) findings.splice(0, 1, ht(hass, "ok"));
  return { level, findings };
}

/* =====================================================================
 * Health card
 * ===================================================================== */
const HEALTH_STYLE = `
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.blk{border:1px solid var(--divider-color);border-radius:12px;padding:10px}
.bh{display:flex;align-items:center;gap:8px}
.amp{width:12px;height:12px;border-radius:50%;flex:none}
.txt{font-size:13px;color:var(--primary-text-color);margin:6px 0 8px;min-height:34px}
.row{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:4px 0;border-top:1px solid var(--divider-color);cursor:pointer}
.row span:first-child{color:var(--secondary-text-color)}
.capbar{position:relative;height:8px;border-radius:4px;background:var(--secondary-background-color);margin:4px 0 2px}
.capbar .mid{position:absolute;left:50%;top:-3px;bottom:-3px;width:2px;background:var(--secondary-text-color)}
.capbar .fill{position:absolute;top:0;bottom:0;border-radius:4px}
.small{font-size:11px;color:var(--secondary-text-color)}
`;

class BydBatteryHealthCard extends BydBatteryBoxCard {
  static getConfigElement() { return document.createElement("byd-battery-health-card-editor"); }
  getCardSize() { return 7; }

  _render() {
    if (!this._config || !this._hass) return;
    this._ensureRoot();
    if (!this._styled) { const st = document.createElement("style"); st.textContent = HEALTH_STYLE; this.shadowRoot.prepend(st); this._styled = true; }
    if (!this._model) this._model = discover(this._hass, this._config.device_id);
    const m = this._model, h = this._hass;
    if (!m) { this._root.innerHTML = `<div class="lbl">${this._t("not_found")}</div>`; return; }
    this._loadTrend(m);
    const ids = [...Object.values(m.bmu.keys), ...m.bms.flatMap((b) => [...Object.values(b.keys), ...b.alarms])];
    const sig = ids.map((id) => (h.states[id] ? h.states[id].state : "")).join("|") + JSON.stringify(this._trend || {});
    if (sig === this._sig) return;
    this._sig = sig;
    const k = m.bmu.keys;
    const box = (label, value, sub, ent) => `<div class="m" data-entity="${ent || ""}"><div class="ml">${label}</div><div class="mv">${value}</div><div class="ms">${sub || "&nbsp;"}</div></div>`;
    const depth = attr(h, k.last_cycle_energy, "depth");
    const nominal = attr(h, k.usable_capacity, "nominal_capacity");
    const results = m.bms.map((b) => assess(h, m, b, this._trend ? this._trend[b.index] : null));
    const worst = Math.max(0, ...results.map((r) => r.level));
    let html = `<div class="top"><div class="ttl">${esc(this._config.title || ht(h, "health_title"))}</div><span class="amp" style="background:${LEVEL_COLOR[worst]}"></span></div>`;
    html += `<div class="metrics">
      ${box(ht(h, "soh"), `${fmt(num(h, k.soh))} %`, "", k.soh)}
      ${box(ht(h, "cycles"), fmt(num(h, k.full_cycles), 0), "", k.full_cycles)}
      ${box(ht(h, "usable"), `${fmt(num(h, k.usable_capacity), 1)} kWh`, nominal ? `/ ${fmt(nominal, 1)} kWh` : "", k.usable_capacity)}
      ${box(ht(h, "last_cycle"), `${fmt(num(h, k.last_cycle_energy), 1)} kWh`, depth != null ? `${ht(h, "depth")} ${fmt(depth, 0)} %` : "", k.last_cycle_energy)}</div>`;
    html += `<div class="grid">${m.bms.map((b, i) => this._block(b, results[i])).join("")}</div>`;
    this._root.innerHTML = html;
  }

  _block(b, res) {
    const h = this._hass, k = b.keys, n = this._model.bms.length;
    const cap = num(h, k.relative_capacity), src = attr(h, k.relative_capacity, "source");
    const used = attr(h, k.relative_capacity, "cycles_used") || 0;
    const d = cap == null ? 0 : Math.max(-10, Math.min(10, cap - 100));
    const lvl = cap == null ? 0 : Math.abs(cap - 100) <= 3 ? 0 : Math.abs(cap - 100) <= 6 ? 1 : 2;
    const fill = `left:${d < 0 ? 50 + d * 5 : 50}%;width:${Math.abs(d) * 5}%;background:${LEVEL_COLOR[lvl]}`;
    const share = num(h, k.current_share);
    const ri = num(h, k.internal_resistance), riN = attr(h, k.internal_resistance, "samples") || 0;
    const weak = num(h, k.weakest_cell), wTop = attr(h, k.weakest_cell, "top_snapshots") || 0, score = attr(h, k.weakest_cell, "score_mv");
    const row = (label, value, ent) => `<div class="row" data-entity="${ent || ""}"><span>${label}</span><span>${value}</span></div>`;
    const collecting = (have, need, what) => `<span class="small">${ht(h, "collecting")} (${have} ${ht(h, "of")} ${need} ${ht(h, what)})</span>`;
    const tr = this._trendPts && this._trendPts[b.index];
    return `<div class="blk">
      <div class="bh"><span class="amp" style="background:${LEVEL_COLOR[res.level]}"></span><span class="tn">BMS ${b.index}</span></div>
      <div class="txt">${res.findings.map(esc).join(" ")}</div>
      <div data-entity="${k.relative_capacity || ""}" style="cursor:pointer">
        <div style="display:flex;justify-content:space-between;font-size:13px"><span style="color:var(--secondary-text-color)">${ht(h, "rel_cap")}</span><span>${fmt(cap, 1)} %</span></div>
        <div class="capbar"><div class="fill" style="${fill}"></div><div class="mid"></div></div>
        <div class="small" style="display:flex;justify-content:space-between"><span>90 %</span><span>${src === "cycles" ? ht(h, "src_cycles", { n: used }) : ht(h, "src_lifetime")}</span><span>110 %</span></div>
      </div>
      ${tr && tr.length > 1 ? `<div style="margin-top:6px">${spark(tr)}<div class="small">${ht(h, "trend")}</div></div>` : ""}
      <div style="margin-top:8px">
      ${row(ht(h, "cur_share"), share == null ? "–" : `${fmt(share, 1)} % <span class="small">(${ht(h, "expected")} ${fmt(cap == null ? 100 / n : cap / n, 1)} %)</span>`, k.current_share)}
      ${row(ht(h, "ri"), ri == null ? collecting(riN, 5, "load_steps") : `${fmt(ri, 1)} mΩ`, k.internal_resistance)}
      ${row(ht(h, "weakest"), weak == null ? collecting(wTop, 3, "full_charges") : `${ht(h, "cell")} ${fmt(weak)} <span class="small">(${score >= 0 ? "+" : ""}${fmt(score, 0)} mV)</span>`, k.weakest_cell)}
      </div></div>`;
  }

  async _loadTrend(m) {
    const now = Date.now();
    if (this._trendLoading || (this._trendAt && now - this._trendAt < 600000)) return;
    const ids = m.bms.map((b) => b.keys.relative_capacity).filter(Boolean);
    if (!ids.length || !this._hass.callWS) return;
    this._trendLoading = true;
    try {
      const S = await this._hass.callWS({ type: "recorder/statistics_during_period", start_time: new Date(now - 90 * 864e5).toISOString(), statistic_ids: ids, period: "day", types: ["mean"] });
      this._trend = {}; this._trendPts = {};
      m.bms.forEach((b) => {
        const pts = (S[b.keys.relative_capacity] || []).filter((p) => p.mean != null).map((p) => p.mean);
        this._trendPts[b.index] = pts;
        this._trend[b.index] = pts.length >= 14 ? pts[pts.length - 1] - pts[0] : null;
      });
    } catch (e) { /* statistics not available yet */ }
    this._trendAt = now; this._trendLoading = false; this._sig = null; this._render();
  }
}

function spark(pts) {
  const W = 200, H = 32, lo = Math.min(...pts, 97), hi = Math.max(...pts, 103);
  const X = (i) => (i / (pts.length - 1)) * W, Y = (v) => H - 2 - ((v - lo) / (hi - lo)) * (H - 4);
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none">
    <line x1="0" x2="${W}" y1="${Y(100)}" y2="${Y(100)}" stroke="var(--divider-color)" stroke-dasharray="3 3"/>
    <polyline fill="none" stroke="var(--primary-color,#03a9f4)" stroke-width="2" points="${pts.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ")}"/></svg>`;
}

/* =====================================================================
 * Compact card (smartphones)
 * ===================================================================== */
const COMPACT_STYLE = `
ha-card{display:block;padding:12px 14px;cursor:pointer}
.c1{display:flex;align-items:center;gap:14px}
.ring{position:relative;width:64px;height:64px;flex:none}
.ring span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:500;color:var(--primary-text-color)}
.pw{font-size:20px;font-weight:500;color:var(--primary-text-color)}
.sub{font-size:13px;color:var(--secondary-text-color)}
.c2{display:grid;grid-template-columns:repeat(auto-fit,minmax(70px,1fr));gap:8px;margin-top:10px}
.chip{display:flex;flex-direction:column;gap:4px}
.cl{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--secondary-text-color)}
.dot{width:9px;height:9px;border-radius:50%}
.strip{display:grid;grid-template-columns:repeat(16,1fr);gap:1px;height:14px}
.strip i{border-radius:1px}
`;

class BydBatteryCompactCard extends HTMLElement {
  static getConfigElement() { return document.createElement("byd-battery-compact-card-editor"); }
  static getStubConfig() { return {}; }
  setConfig(config) {
    this._config = { reserve_soc: 0, power_invert: false, scale_mv: 15, ...config, colors: { ...DEFAULT_COLORS, ...(config.colors || {}) } };
    this._sig = null; if (this._hass) this._render();
  }
  set hass(hass) {
    this._hass = hass;
    if (hass.entities !== this._ref) { this._ref = hass.entities; this._model = null; }
    if (this._popup) this._popup.card.hass = hass;
    this._render();
  }
  getCardSize() { return 3; }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `<style>${COMPACT_STYLE}</style><ha-card><div id="c"></div></ha-card>`;
      this.shadowRoot.querySelector("ha-card").addEventListener("click", () => this._openPopup());
    }
    const h = this._hass;
    if (!this._model) this._model = discover(h, this._config.device_id);
    const m = this._model, root = this.shadowRoot.getElementById("c");
    if (!m) { root.textContent = "BYD Battery-Box: –"; return; }
    const k = m.bmu.keys;
    const sig = [k.soc, k.power, k.remaining_energy, this._config.power_entity, ...m.bms.flatMap((b) => [...b.cells, ...Object.values(b.keys), ...b.alarms])]
      .map((id) => (id && h.states[id] ? h.states[id].state : "")).join("|");
    if (sig === this._sig) return;
    this._sig = sig;

    const soc = num(h, k.soc);
    let p = this._config.power_entity ? num(h, this._config.power_entity) : num(h, k.power);
    if (p != null && this._config.power_invert) p = -p;
    let dir = ht(h, "idle"), eta = "";
    if (p != null && Math.abs(p) >= 50) {
      const rem = num(h, k.remaining_energy), cap = num(h, k.usable_capacity);
      const reserve = cap != null ? (cap * this._config.reserve_soc) / 100 : 0;
      const kwh = p > 0 ? (rem != null ? rem - reserve : null) : (rem != null && cap != null ? cap - rem : null);
      dir = ht(h, p > 0 ? "discharging" : "charging");
      if (kwh != null && kwh > 0) {
        const hrs = kwh / (Math.abs(p) / 1000), hh = Math.floor(hrs), mm = Math.round((hrs - hh) * 60);
        eta = `${ht(h, p > 0 ? "empty_in" : "full_in")} ${hh > 0 ? `${hh} h ` : ""}${mm} min`;
      }
    }
    const r = 28, C = 2 * Math.PI * r, frac = Math.max(0, Math.min(1, (soc || 0) / 100));
    const ringColor = soc == null ? "var(--disabled-color)" : soc < 20 ? LEVEL_COLOR[2] : soc < 40 ? LEVEL_COLOR[1] : LEVEL_COLOR[0];
    const ring = `<div class="ring"><svg viewBox="0 0 64 64" width="64" height="64"><circle cx="32" cy="32" r="${r}" fill="none" stroke="var(--secondary-background-color)" stroke-width="6"/>
      <circle cx="32" cy="32" r="${r}" fill="none" stroke="${ringColor}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${(C * frac).toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90 32 32)"/></svg><span>${fmt(soc)} %</span></div>`;
    const chips = m.bms.map((b) => {
      const a = assess(h, m, b);
      const volts = b.cells.map((id) => num(h, id)), ok = volts.filter((v) => v != null);
      const avg = ok.reduce((s, v) => s + v, 0) / (ok.length || 1);
      const strip = volts.map((v) => `<i style="background:${v == null ? "var(--disabled-color)" : devColor(v - avg, this._config.scale_mv, this._config.colors)}"></i>`).join("");
      return `<div class="chip" title="${esc(a.findings.join(" "))}"><div class="cl"><span class="dot" style="background:${LEVEL_COLOR[a.level]}"></span>BMS ${b.index} · ${fmt(num(h, b.keys.soc), 0)} %</div><div class="strip">${strip}</div></div>`;
    }).join("");
    root.innerHTML = `<div class="c1">${ring}<div><div class="pw">${p == null ? "–" : fmt(Math.abs(p))} W</div><div class="sub">${dir}${eta ? " · " + eta : ""}</div></div></div><div class="c2">${chips}</div>`;
  }

  _openPopup() {
    if (this._popup) return;
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.5);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:max(12px,env(safe-area-inset-top)) 8px 12px";
    const wrap = document.createElement("div");
    wrap.style.cssText = "position:relative;width:100%;max-width:900px";
    const close = document.createElement("button");
    close.textContent = "✕";
    close.setAttribute("aria-label", "Close");
    close.style.cssText = "position:absolute;top:8px;right:8px;z-index:1;border:0;border-radius:50%;width:32px;height:32px;font-size:16px;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color)";
    const card = document.createElement(CARD_TYPE);
    card.setConfig({ ...(this._config.popup_card || {}), colors: this._config.colors, scale_mv: this._config.scale_mv });
    card.hass = this._hass;
    wrap.append(close, card); overlay.append(wrap); document.body.append(overlay);
    const done = () => { overlay.remove(); document.removeEventListener("keydown", esc_); this._popup = null; };
    const esc_ = (e) => { if (e.key === "Escape") done(); };
    overlay.addEventListener("click", (e) => { if (e.target === overlay) done(); });
    close.addEventListener("click", done);
    document.addEventListener("keydown", esc_);
    // more-info from inside the popup: forward to Home Assistant's root element
    overlay.addEventListener("hass-more-info", (e) => {
      const ha = document.querySelector("home-assistant");
      if (ha && e.target !== ha) { e.stopPropagation(); done(); ha.dispatchEvent(new CustomEvent("hass-more-info", { detail: e.detail, bubbles: true, composed: true })); }
    });
    this._popup = { overlay, card };
  }
}

/* ---------- simple editors for the two additional cards ---------- */
class BydSimpleEditor extends HTMLElement {
  set hass(hass) { this._hass = hass; this._build(); }
  setConfig(config) { this._config = { ...config }; this._build(true); }
  _build(sync) {
    if (!this._config || !this._hass) return;
    const l = (this._hass.language || "en").startsWith("de") ? "de" : "en";
    if (!this._built) {
      this._built = true;
      this.innerHTML = this.constructor.FIELDS.map(([key, type, label]) =>
        `<label style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin:8px 0"><span>${label[l]}</span><input data-key="${key}" type="${type}" ${type === "number" ? 'style="width:80px"' : 'style="flex:1;max-width:260px"'}></label>`).join("");
      this.querySelectorAll("input").forEach((el) => el.addEventListener("change", () => {
        const c = { ...this._config }, key = el.dataset.key;
        if (el.type === "checkbox") c[key] = el.checked;
        else if (el.type === "number") c[key] = Number(el.value) || 0;
        else if (el.value) c[key] = el.value; else delete c[key];
        this._config = c;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: c }, bubbles: true, composed: true }));
      }));
      sync = true;
    }
    if (sync) this.querySelectorAll("input").forEach((el) => {
      const v = this._config[el.dataset.key];
      if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? "";
    });
  }
}
class BydHealthEditor extends BydSimpleEditor {}
BydHealthEditor.FIELDS = [["title", "text", { de: "Titel", en: "Title" }]];
class BydCompactEditor extends BydSimpleEditor {}
BydCompactEditor.FIELDS = [
  ["power_entity", "text", { de: "Schnellerer Leistungssensor (optional, z. B. Sunny Island)", en: "Faster power sensor (optional, e.g. inverter)" }],
  ["power_invert", "checkbox", { de: "Vorzeichen des Leistungssensors umkehren", en: "Invert sign of the power sensor" }],
  ["reserve_soc", "number", { de: "Entladegrenze für Restlaufzeit (%)", en: "Discharge limit for remaining time (%)" }],
];

if (!customElements.get(CARD_TYPE)) customElements.define(CARD_TYPE, BydBatteryBoxCard);
if (!customElements.get(`${CARD_TYPE}-editor`)) customElements.define(`${CARD_TYPE}-editor`, BydBatteryBoxCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TYPE))
  window.customCards.push({ type: CARD_TYPE, name: "BYD Battery-Box", description: "Cells, temperatures and history of a BYD Battery-Box", preview: true, documentationURL: "https://github.com/plumsl/byd_battery_box" });
for (const [type, cls, editor, name, description] of [
  ["byd-battery-health-card", BydBatteryHealthCard, BydHealthEditor, "BYD Battery-Box – Zustand", "Health analysis per module with assessment"],
  ["byd-battery-compact-card", BydBatteryCompactCard, BydCompactEditor, "BYD Battery-Box – Kompakt", "Compact card for smartphones, opens the full card"],
]) {
  if (!customElements.get(type)) customElements.define(type, cls);
  if (!customElements.get(`${type}-editor`)) customElements.define(`${type}-editor`, editor);
  if (!window.customCards.some((c) => c.type === type))
    window.customCards.push({ type, name, description, preview: true, documentationURL: "https://github.com/plumsl/byd_battery_box" });
}
console.info(`%c BYD-BATTERY-BOX-CARD %c ${CARD_VERSION} `, "background:#1D9E75;color:#fff", "background:#444;color:#fff");
