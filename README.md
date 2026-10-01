# BYD Battery-Box for Home Assistant

Local Home Assistant integration for the **BYD Battery-Box Premium LVL**. It reads the
BMU *and every single BMS* directly over the LAN – no cloud, no extra hardware.

> 🇩🇪 Deutsche Kurzanleitung weiter unten.

## Features

- **BMU overview** (default every 30 s): SOC, SOH, voltage, current, power, min/max cell
  voltage and temperature, energy charged/discharged (Energy dashboard ready),
  round-trip efficiency, status/error flags, inverter configuration.
- **Per BMS** (default every 5 min): SOC, SOH, voltage, current, power, 16 cell voltages,
  8 temperatures, cell voltage spread, balancing, energy counters, status flags.
- One device per BMS, linked to the BMU device – like in *Be Connect Plus*.
- **Derived values**: remaining energy, usable capacity (from SOH), full cycles, SOC spread
  between the BMS, system-wide cell spread, average cell voltage.
- **Alarms** with adjustable thresholds (cell over/undervoltage, cell spread – separate limit
  for a full battery –, temperature, SOC imbalance, BMU/BMS fault flags). They show up as
  *problem* binary sensors and under *Settings → Repairs*, and clear themselves.
- **Dashboard card** (`custom:byd-battery-box-card`), installed automatically with the
  integration: all batteries side by side, every cell coloured by its deviation, the
  temperature sensors between the cells, plus a *History* view with long-term SOH, cell
  spread trend, SOC per BMS and a 30-day cell heatmap. Colours are configurable in the
  visual editor.
- Sensors become *unavailable* on communication errors instead of showing stale values.
- *Download diagnostics* includes the raw frames – please attach it to issues.

## Tested hardware

| Battery | BMS | Firmware | Inverter | Status |
|---|---|---|---|---|
| Battery-Box Premium LVL 15.4 | 3 | BMU V1.35, BMS V1.17 | SMA Sunny Island | ✅ verified against Be Connect Plus |

HVS/HVM are **not** tested yet. Reports (with diagnostics) are very welcome.

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → `https://github.com/plumsl/byd_battery_box`, type *Integration*.
2. Install **BYD Battery-Box**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → BYD Battery-Box*, enter the BMU IP address.

Polling intervals can be changed later under *Configure*.

## Dashboard card

After installing, edit a dashboard → *Add card* → search for **BYD Battery-Box**. All
options are available in the visual editor. YAML example:

```yaml
type: custom:byd-battery-box-card
title: Batteriespeicher
scale_mv: 15            # deviation (mV) that reaches the full colour
swap_modules: false     # B1 = cells 1-8 is drawn at the bottom
show_balancing_cells: false   # experimental, bit order not yet confirmed
colors:
  low: "#378ADD"
  mid: "#5DCAA5"
  high: "#EF9F27"
  balancing: "#E24B4A"
  cold: "#378ADD"     # 10 °C and below
  normal: "#E3E1D9"   # 25 °C
  warm: "#D85A30"     # 40 °C and above
```

A complete example dashboard is in [`examples/dashboard.yaml`](examples/dashboard.yaml).
Click on any cell, temperature or value to open its history.

Long-term charts use Home Assistant's statistics, which are collected from installation
onwards – the history view fills up over time.

## Important notes

- The BMU accepts **only one TCP connection** at a time. While *Be Connect* is connected,
  updates fail and the sensors are unavailable for a moment – this is expected.
- Do **not** run another BYD integration (e.g. `byd_hvs`) against the same battery at the same time.
- Current and power reported by the BMU lag behind fast load changes by roughly 30–60 s.
  For a second-accurate power reading use your inverter's battery sensor.
- Sign convention: **positive current/power = discharging**, negative = charging.
- Cells 1–8 are assumed to sit in the lower module B1 and temperature sensors 1–4 in B1
  (derived from measurements, not from BYD documentation). Use `swap_modules` if needed.

## Credits

The register layout builds on the reverse-engineering work in
[bbr111/byd_hvs](https://github.com/bbr111/byd_hvs) and ioBroker.bydhvs, extended and
verified for the LVL with 3 BMS.

## License

GPL-3.0

---

## 🇩🇪 Kurzanleitung

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/plumsl/byd_battery_box`, Typ *Integration*.
2. **BYD Battery-Box** installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → BYD Battery-Box*, IP-Adresse der BMU eingeben.

Be Connect vorher schließen – die BMU akzeptiert nur eine Verbindung gleichzeitig.

![Dashboard card: three LVL batteries side by side with every cell and temperature sensor](https://raw.githubusercontent.com/plumsl/byd_battery_box/main/docs/images/card-live.png)

