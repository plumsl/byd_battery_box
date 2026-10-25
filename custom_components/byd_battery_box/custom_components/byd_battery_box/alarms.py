"""Alarm evaluation with hysteresis; raises Home Assistant repair issues."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    ALARM_OPTIONS,
    CONF_CELL_HIGH,
    CONF_CELL_LOW,
    CONF_SOC_DIFF,
    CONF_SPREAD,
    CONF_SPREAD_FULL,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    DOMAIN,
    SPREAD_FULL_SOC,
)
from .protocol import BmsData, BmuStatus

BMS_ALARMS = (
    "cell_voltage_high",
    "cell_voltage_low",
    "cell_spread_high",
    "temperature_high",
    "temperature_low",
    "bms_fault",
)
BMU_ALARMS = ("system_fault", "soc_imbalance")

ERROR_ALARMS = {"bms_fault", "system_fault", "cell_voltage_high", "cell_voltage_low"}


@dataclass
class AlarmState:
    active: bool = False
    details: dict[str, Any] = field(default_factory=dict)


def _hyst(active: bool, value: float, limit: float, hyst: float, above: bool) -> bool:
    """Switch on beyond the limit, off only after returning by `hyst`."""
    if above:
        return value > (limit - hyst if active else limit)
    return value < (limit + hyst if active else limit)


class AlarmManager:
    """Keeps alarm states for the BMU (index 0) and every BMS (1..n)."""

    def __init__(self, hass: HomeAssistant, entry_id: str, serial: str,
                 options: dict[str, Any], bms_count: int) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.serial = serial
        self.opt = {k: options.get(k, v[0]) for k, v in ALARM_OPTIONS.items()}
        self.states: dict[tuple[int, str], AlarmState] = {
            (0, key): AlarmState() for key in BMU_ALARMS
        }
        for index in range(1, bms_count + 1):
            for key in BMS_ALARMS:
                self.states[(index, key)] = AlarmState()
        self._listeners: list[Callable[[], None]] = []

    # -- public --------------------------------------------------------------
    def get(self, index: int, key: str) -> AlarmState:
        return self.states[(index, key)]

    @callback
    def update_status(self, status: BmuStatus | None) -> None:
        if status is None:
            return
        self._set(0, "system_fault", status.error_code != 0,
                  {"error_code": status.error_code, "errors": status.errors})

    @callback
    def update_bms(self, data: dict[int, BmsData] | None) -> None:
        if not data:
            return
        o = self.opt
        for i, b in data.items():
            st = lambda k: self.states[(i, k)].active  # noqa: E731
            self._set(i, "cell_voltage_high",
                      _hyst(st("cell_voltage_high"), b.max_cell_voltage, o[CONF_CELL_HIGH], 20, True),
                      {"value": b.max_cell_voltage, "cell": b.max_cell_no, "limit": o[CONF_CELL_HIGH]})
            self._set(i, "cell_voltage_low",
                      _hyst(st("cell_voltage_low"), b.min_cell_voltage, o[CONF_CELL_LOW], 20, False),
                      {"value": b.min_cell_voltage, "cell": b.min_cell_no, "limit": o[CONF_CELL_LOW]})
            limit = o[CONF_SPREAD_FULL] if b.soc >= SPREAD_FULL_SOC else o[CONF_SPREAD]
            self._set(i, "cell_spread_high",
                      _hyst(st("cell_spread_high"), b.cell_spread, limit, 5, True),
                      {"value": b.cell_spread, "limit": limit, "soc": b.soc})
            self._set(i, "temperature_high",
                      _hyst(st("temperature_high"), b.max_temp, o[CONF_TEMP_HIGH], 2, True),
                      {"value": b.max_temp, "sensor": b.max_temp_no, "limit": o[CONF_TEMP_HIGH]})
            self._set(i, "temperature_low",
                      _hyst(st("temperature_low"), b.min_temp, o[CONF_TEMP_LOW], 2, False),
                      {"value": b.min_temp, "sensor": b.min_temp_no, "limit": o[CONF_TEMP_LOW]})
            self._set(i, "bms_fault", bool(b.status),
                      {"status_code": b.status_code, "flags": b.status})
        socs = [b.soc for b in data.values()]
        diff = round(max(socs) - min(socs), 1) if len(socs) > 1 else 0
        self._set(0, "soc_imbalance",
                  _hyst(self.states[(0, "soc_imbalance")].active, diff, o[CONF_SOC_DIFF], 2, True),
                  {"value": diff, "limit": o[CONF_SOC_DIFF]})

    @callback
    def clear_issues(self) -> None:
        for index, key in self.states:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(index, key))

    # -- internals -----------------------------------------------------------
    def _issue_id(self, index: int, key: str) -> str:
        scope = "bmu" if index == 0 else f"bms{index}"
        return f"{self.serial}_{scope}_{key}"

    def _set(self, index: int, key: str, active: bool, details: dict[str, Any]) -> None:
        state = self.states[(index, key)]
        state.details = details
        if active == state.active:
            return
        state.active = active
        issue_id = self._issue_id(index, key)
        if active:
            placeholders = {"device": "BMU" if index == 0 else f"BMS {index}"}
            placeholders.update({k: str(v) for k, v in details.items() if not isinstance(v, list)})
            for k in ("errors", "flags"):
                if k in details:
                    placeholders[k] = ", ".join(details[k]) or "-"
            ir.async_create_issue(
                self.hass, DOMAIN, issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR if key in ERROR_ALARMS else ir.IssueSeverity.WARNING,
                translation_key=key,
                translation_placeholders=placeholders,
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
