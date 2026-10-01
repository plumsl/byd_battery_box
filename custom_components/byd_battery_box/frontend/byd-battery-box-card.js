/*
 * BYD Battery-Box card for Home Assistant
 * Shipped with the byd_battery_box integration – no separate installation needed.
 * https://github.com/plumsl/byd_battery_box
 */
const CARD_VERSION = "0.2.0-beta.2";
const DOMAIN = "byd_battery_box";
const CARD_TYPE = "byd-battery-box-card";

const DEFAULT_COLORS = {
  low: "#378ADD",
  mid: "#5DCAA5",
  high: "#EF9F27",
  balancing: "#E24B4A",
  cold: "#85B7EB",
  warm: "#F0997B",
};
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
const tempColor = (v, c) => mix(c.cold, c.warm, Math.max(0, Math.min(1, (v - 15) / 25)));
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
ha-card{padding:16px;overflow:hidden}
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
.cell{height:74px;border-radius:3px;display:flex;align-items:center;justify-content:center;font-size:11px;cursor:pointer;box-sizing:border-box}
.cell span{writing-mode:vertical-rl;transform:rotate(180deg)}
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
    const mod = (from, name) => {
      let cells = "";
      for (let i = from; i < from + 8; i++) {
        const v = volts[i], id = b.cells[i];
        const bg = v == null ? "var(--disabled-color,#bdbdbd)" : devColor(v - avg, this._config.scale_mv, c);
        const bal = balCells.includes(i + 1);
        const tip = `BMS ${b.index} · ${this._t("cell")} ${i + 1}: ${fmt(v)} mV (${v - avg >= 0 ? "+" : ""}${fmt(v - avg)} mV)${bal ? " · " + this._t("balancing") : ""}`;
        cells += `<div class="cell" data-entity="${id || ""}" data-tip="${esc(tip)}" style="background:${bg};color:${textOn(bg.startsWith("#") ? bg : "#bdbdbd")};${bal ? `box-shadow:inset 0 0 0 2px ${c.balancing}` : ""}"><span>${fmt(v)}</span></div>`;
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
      ${this._config.swap_modules ? lower + upper : upper + lower}</div>`;
  }

  _legend() {
    const c = this._config.colors, s = this._config.scale_mv;
    return `<div class="legend"><span>−${s} mV</span><div class="grad" style="background:linear-gradient(90deg,${c.low},${c.mid},${c.high})"></div><span>+${s} mV</span>
      <span style="margin-left:auto"><span class="dot" style="background:${c.cold}"></span>15 °C <span class="dot" style="background:${c.warm};margin-left:6px"></span>40 °C</span></div>`;
  }

  /* ---------- history ---------- */
  async _renderHistory(m) {
    this._root.innerHTML = this._header() + `<div class="lbl">${this._t("loading")}</div>`;
    const now = Date.now();
    if (!this._stats || now - this._statsAt > 600000) {
      const ids = new Set([m.bmu.keys.soh]);
      m.bms.forEach((b) => { [b.keys.soh, b.keys.cell_spread, b.keys.soc, ...b.cells].forEach((id) => id && ids.add(id)); });
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
  ["cold", { de: "Temperatur kalt", en: "Temperature cold" }],
  ["warm", { de: "Temperatur warm", en: "Temperature warm" }],
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

if (!customElements.get(CARD_TYPE)) customElements.define(CARD_TYPE, BydBatteryBoxCard);
if (!customElements.get(`${CARD_TYPE}-editor`)) customElements.define(`${CARD_TYPE}-editor`, BydBatteryBoxCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TYPE))
  window.customCards.push({ type: CARD_TYPE, name: "BYD Battery-Box", description: "Cells, temperatures and history of a BYD Battery-Box", preview: true, documentationURL: "https://github.com/plumsl/byd_battery_box" });
console.info(`%c BYD-BATTERY-BOX-CARD %c ${CARD_VERSION} `, "background:#1D9E75;color:#fff", "background:#444;color:#fff");
