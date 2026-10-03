# Changelog

## 0.3.0
- **Battery health analysis** per BMS (state survives restarts): relative capacity from the
  energy share between full charges, current share, weakest cell, internal resistance
  (experimental) and the energy of the last full-to-full cycle
- **Health card** `custom:byd-battery-health-card` with traffic light, plain-language
  assessment, capacity bar, 90-day trend
- **Compact card** `custom:byd-battery-compact-card` for smartphones: SOC ring, power,
  remaining time, traffic light and cell strip per BMS; tap opens the full card as a popup
- Live card: capacity/share/Ri per BMS, weakest cell marked, new history charts,
  three-step temperature colours (configurable neutral colour)
- Fix: BMS status bit 2 is the normal end-of-charge state ("Charge stop: cell voltage high"),
  not a fault – no more false "BMS fault" alarms on full charge
- Internal resistance: works with cell-data intervals up to 15 min
- Current share is averaged over ~2 days
- Popup close button no longer covers the view switch; heatmap labels no longer overlap
- Bilingual wiki: https://github.com/plumsl/byd_battery_box/wiki

## 0.2.1
- Fix: the dashboard card is now registered automatically as a dashboard resource
  (Settings → Dashboards → Resources), the same way HACS cards are loaded. Existing manual
  entries for the card are updated to the current version automatically.

## 0.2.0
- Dashboard card `custom:byd-battery-box-card`, installed automatically with the integration:
  live view with every cell and temperature sensor, history view with SOH, cell spread,
  SOC per BMS and a 30-day cell heatmap; colours configurable in the visual editor
- Alarm binary sensors and repair issues with configurable thresholds
- New sensors: remaining energy, usable capacity, full cycles, SOC spread between BMS,
  system cell spread, average cell voltage
- Cell and temperature sensors expose `bms`, `cell`/`sensor` and `module` attributes
- Screenshot in README

## 0.1.1
- Configurable polling intervals with limits
- Device linking compatible with Home Assistant 2026.8+

## 0.1.0
- First release
