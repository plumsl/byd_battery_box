# Changelog

## 0.2.0-beta.3
- Temperature colours use a three-step scale (cold 10 °C → neutral 25 °C → warm 40 °C);
  the neutral colour is configurable

## 0.2.0-beta.2
- Dashboard card is registered more robustly (retry after start, warning in the log if it fails)
- Screenshot in README

## 0.2.0-beta.1
- Dashboard card `custom:byd-battery-box-card` (live view and history view), configurable colours
- Alarm binary sensors and repair issues with configurable thresholds (second options step)
- New sensors: remaining energy, usable capacity, full cycles, SOC spread between BMS,
  system cell spread, average cell voltage
- Cell and temperature sensors expose `bms`, `cell`/`sensor` and `module` attributes

## 0.1.1
- Configurable polling intervals with limits
- Device linking compatible with Home Assistant 2026.8+

## 0.1.0
- First release
