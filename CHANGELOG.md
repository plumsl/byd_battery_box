# Changelog

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
