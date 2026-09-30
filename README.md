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

## Important notes

- The BMU accepts **only one TCP connection** at a time. While *Be Connect* is connected,
  updates fail and the sensors are unavailable for a moment – this is expected.
- Do **not** run another BYD integration (e.g. `byd_hvs`) against the same battery at the same time.
- Current and power reported by the BMU lag behind fast load changes by roughly 30–60 s.
  For a second-accurate power reading use your inverter's battery sensor.
- Sign convention: **positive current/power = discharging**, negative = charging.

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
