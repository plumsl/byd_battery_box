"""Sensors for the BYD Battery-Box (BMU + every BMS)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, NOMINAL_KWH_PER_BMS
from .coordinator import BydConfigEntry
from .protocol import CELLS_PER_BMS, TEMPS_PER_BMS, BmsData, BmuStatus

M = SensorStateClass.MEASUREMENT
V = UnitOfElectricPotential.VOLT
MV = UnitOfElectricPotential.MILLIVOLT
C = UnitOfTemperature.CELSIUS
KWH = UnitOfEnergy.KILO_WATT_HOUR
DIAG = EntityCategory.DIAGNOSTIC


@dataclass(frozen=True, kw_only=True)
class BydSensorDescription(SensorEntityDescription):
    """Sensor description with value getter."""

    value_fn: Callable[[Any], Any]
    attr_fn: Callable[[Any], dict[str, Any]] | None = None


def _status_text(errors: list[str]) -> str:
    return "Normal" if not errors else ", ".join(errors)


# --- BMU -------------------------------------------------------------------
BMU_SENSORS: tuple[BydSensorDescription, ...] = (
    BydSensorDescription(key="soc", translation_key="soc", native_unit_of_measurement=PERCENTAGE,
                         device_class=SensorDeviceClass.BATTERY, state_class=M,
                         value_fn=lambda s: s.soc),
    BydSensorDescription(key="soh", translation_key="soh", native_unit_of_measurement=PERCENTAGE,
                         state_class=M, value_fn=lambda s: s.soh),
    BydSensorDescription(key="voltage", translation_key="voltage", native_unit_of_measurement=V,
                         device_class=SensorDeviceClass.VOLTAGE, state_class=M,
                         suggested_display_precision=2, value_fn=lambda s: s.voltage),
    BydSensorDescription(key="output_voltage", translation_key="output_voltage",
                         native_unit_of_measurement=V, device_class=SensorDeviceClass.VOLTAGE,
                         state_class=M, suggested_display_precision=2, entity_category=DIAG,
                         value_fn=lambda s: s.output_voltage),
    BydSensorDescription(key="current", translation_key="current",
                         native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                         device_class=SensorDeviceClass.CURRENT, state_class=M,
                         suggested_display_precision=1, value_fn=lambda s: s.current),
    BydSensorDescription(key="power", translation_key="power", native_unit_of_measurement=UnitOfPower.WATT,
                         device_class=SensorDeviceClass.POWER, state_class=M,
                         suggested_display_precision=0, value_fn=lambda s: s.power),
    BydSensorDescription(key="max_cell_voltage", translation_key="max_cell_voltage",
                         native_unit_of_measurement=V, device_class=SensorDeviceClass.VOLTAGE,
                         state_class=M, suggested_display_precision=2,
                         value_fn=lambda s: s.max_cell_voltage),
    BydSensorDescription(key="min_cell_voltage", translation_key="min_cell_voltage",
                         native_unit_of_measurement=V, device_class=SensorDeviceClass.VOLTAGE,
                         state_class=M, suggested_display_precision=2,
                         value_fn=lambda s: s.min_cell_voltage),
    BydSensorDescription(key="max_temperature", translation_key="max_temperature",
                         native_unit_of_measurement=C, device_class=SensorDeviceClass.TEMPERATURE,
                         state_class=M, value_fn=lambda s: s.max_cell_temp),
    BydSensorDescription(key="min_temperature", translation_key="min_temperature",
                         native_unit_of_measurement=C, device_class=SensorDeviceClass.TEMPERATURE,
                         state_class=M, value_fn=lambda s: s.min_cell_temp),
    BydSensorDescription(key="charge_energy", translation_key="charge_energy",
                         native_unit_of_measurement=KWH, device_class=SensorDeviceClass.ENERGY,
                         state_class=SensorStateClass.TOTAL_INCREASING, suggested_display_precision=1,
                         value_fn=lambda s: s.charge_energy),
    BydSensorDescription(key="discharge_energy", translation_key="discharge_energy",
                         native_unit_of_measurement=KWH, device_class=SensorDeviceClass.ENERGY,
                         state_class=SensorStateClass.TOTAL_INCREASING, suggested_display_precision=1,
                         value_fn=lambda s: s.discharge_energy),
    BydSensorDescription(key="efficiency", translation_key="efficiency",
                         native_unit_of_measurement=PERCENTAGE, state_class=M,
                         suggested_display_precision=1, value_fn=lambda s: s.efficiency),
    BydSensorDescription(key="status", translation_key="status",
                         value_fn=lambda s: _status_text(s.errors),
                         attr_fn=lambda s: {"error_code": s.error_code, "errors": s.errors}),
)

# --- BMS -------------------------------------------------------------------
BMS_SENSORS: tuple[BydSensorDescription, ...] = (
    BydSensorDescription(key="soc", translation_key="soc", native_unit_of_measurement=PERCENTAGE,
                         device_class=SensorDeviceClass.BATTERY, state_class=M,
                         suggested_display_precision=1, value_fn=lambda b: b.soc),
    BydSensorDescription(key="soh", translation_key="soh", native_unit_of_measurement=PERCENTAGE,
                         state_class=M, value_fn=lambda b: b.soh),
    BydSensorDescription(key="voltage", translation_key="voltage", native_unit_of_measurement=V,
                         device_class=SensorDeviceClass.VOLTAGE, state_class=M,
                         suggested_display_precision=1, value_fn=lambda b: b.voltage),
    BydSensorDescription(key="current", translation_key="current",
                         native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                         device_class=SensorDeviceClass.CURRENT, state_class=M,
                         suggested_display_precision=1, value_fn=lambda b: b.current),
    BydSensorDescription(key="power", translation_key="power", native_unit_of_measurement=UnitOfPower.WATT,
                         device_class=SensorDeviceClass.POWER, state_class=M,
                         suggested_display_precision=0, value_fn=lambda b: b.power),
    BydSensorDescription(key="max_cell_voltage", translation_key="max_cell_voltage",
                         native_unit_of_measurement=MV, device_class=SensorDeviceClass.VOLTAGE,
                         state_class=M, value_fn=lambda b: b.max_cell_voltage,
                         attr_fn=lambda b: {"cell": b.max_cell_no}),
    BydSensorDescription(key="min_cell_voltage", translation_key="min_cell_voltage",
                         native_unit_of_measurement=MV, device_class=SensorDeviceClass.VOLTAGE,
                         state_class=M, value_fn=lambda b: b.min_cell_voltage,
                         attr_fn=lambda b: {"cell": b.min_cell_no}),
    BydSensorDescription(key="cell_spread", translation_key="cell_spread",
                         native_unit_of_measurement=MV, device_class=SensorDeviceClass.VOLTAGE,
                         state_class=M, value_fn=lambda b: b.cell_spread),
    BydSensorDescription(key="max_temperature", translation_key="max_temperature",
                         native_unit_of_measurement=C, device_class=SensorDeviceClass.TEMPERATURE,
                         state_class=M, value_fn=lambda b: b.max_temp,
                         attr_fn=lambda b: {"sensor": b.max_temp_no}),
    BydSensorDescription(key="min_temperature", translation_key="min_temperature",
                         native_unit_of_measurement=C, device_class=SensorDeviceClass.TEMPERATURE,
                         state_class=M, value_fn=lambda b: b.min_temp,
                         attr_fn=lambda b: {"sensor": b.min_temp_no}),
    BydSensorDescription(key="balancing", translation_key="balancing", state_class=M,
                         value_fn=lambda b: b.balancing_count,
                         attr_fn=lambda b: {"bits": b.balancing_bits,
                                            "cells_experimental": b.balancing_cells}),
    BydSensorDescription(key="cell_average", translation_key="cell_average",
                         native_unit_of_measurement=MV, device_class=SensorDeviceClass.VOLTAGE,
                         state_class=M, suggested_display_precision=0,
                         value_fn=lambda b: b.cell_average),
    BydSensorDescription(key="charge_energy", translation_key="charge_energy",
                         native_unit_of_measurement=KWH, device_class=SensorDeviceClass.ENERGY,
                         state_class=SensorStateClass.TOTAL_INCREASING, suggested_display_precision=1,
                         value_fn=lambda b: b.charge_energy),
    BydSensorDescription(key="discharge_energy", translation_key="discharge_energy",
                         native_unit_of_measurement=KWH, device_class=SensorDeviceClass.ENERGY,
                         state_class=SensorStateClass.TOTAL_INCREASING, suggested_display_precision=1,
                         value_fn=lambda b: b.discharge_energy),
    BydSensorDescription(key="status", translation_key="status",
                         value_fn=lambda b: _status_text(b.status),
                         attr_fn=lambda b: {"status_code": b.status_code, "flags": b.status,
                                            "firmware_raw": b.firmware_raw, **b.extra}),
)


def bmu_device_info(info) -> DeviceInfo:
    """Device info of the BMU (parent device)."""
    return DeviceInfo(
        identifiers={(DOMAIN, info.serial)},
        manufacturer=MANUFACTURER,
        name="BYD Battery-Box",
        model=f"Battery-Box Premium {info.battery_type}",
        serial_number=info.serial,
        sw_version=f"BMU {info.bmu_firmware}",
    )


def bms_device_info(hass: HomeAssistant, entry: BydConfigEntry, rt, index: int) -> DeviceInfo:
    """Device info of one BMS, linked to the BMU."""
    serial = rt.info.serial
    # HA >= 2026.8 links child devices by registry id (via_device is deprecated),
    # older versions only know the via_device identifier tuple.
    if "via_device_id" in DeviceInfo.__annotations__:
        bmu_entry = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, **bmu_device_info(rt.info)
        )
        via: dict = {"via_device_id": bmu_entry.id}
    else:
        via = {"via_device": (DOMAIN, serial)}
    bms = (rt.details.data or {}).get(index)
    return DeviceInfo(
        identifiers={(DOMAIN, f"{serial}_bms{index}")},
        manufacturer=MANUFACTURER,
        name=f"BYD BMS {index}",
        model=f"{rt.info.battery_type} BMS",
        serial_number=bms.serial if bms else None,
        sw_version=rt.info.bms_firmware,
        **via,
    )


async def async_setup_entry(hass: HomeAssistant, entry: BydConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    rt = entry.runtime_data
    serial = rt.info.serial
    bmu_device = bmu_device_info(rt.info)
    nominal = rt.info.bms_count * NOMINAL_KWH_PER_BMS

    entities: list[SensorEntity] = [
        BmuSensor(rt.status, desc, serial, bmu_device) for desc in BMU_SENSORS
    ]
    entities += [
        BmuSensor(rt.status, BydSensorDescription(
            key="remaining_energy", translation_key="remaining_energy",
            native_unit_of_measurement=KWH, device_class=SensorDeviceClass.ENERGY_STORAGE,
            state_class=M, suggested_display_precision=1,
            value_fn=lambda s: round(nominal * s.soh / 100 * s.soc / 100, 2),
        ), serial, bmu_device),
        BmuSensor(rt.status, BydSensorDescription(
            key="usable_capacity", translation_key="usable_capacity",
            native_unit_of_measurement=KWH, device_class=SensorDeviceClass.ENERGY_STORAGE,
            state_class=M, suggested_display_precision=1,
            value_fn=lambda s: round(nominal * s.soh / 100, 2),
            attr_fn=lambda s: {"nominal_capacity": round(nominal, 2)},
        ), serial, bmu_device),
        BmuSensor(rt.status, BydSensorDescription(
            key="full_cycles", translation_key="full_cycles", state_class=M,
            suggested_display_precision=1,
            value_fn=lambda s: round(s.discharge_energy / nominal, 2),
        ), serial, bmu_device),
        BmuSensor(rt.details, BydSensorDescription(
            key="soc_spread", translation_key="soc_spread",
            native_unit_of_measurement=PERCENTAGE, state_class=M, suggested_display_precision=1,
            value_fn=lambda d: round(max(b.soc for b in d.values()) - min(b.soc for b in d.values()), 1),
            attr_fn=lambda d: {f"bms_{i}": b.soc for i, b in d.items()},
        ), serial, bmu_device),
        BmuSensor(rt.details, BydSensorDescription(
            key="system_cell_spread", translation_key="system_cell_spread",
            native_unit_of_measurement=MV, device_class=SensorDeviceClass.VOLTAGE, state_class=M,
            value_fn=lambda d: max(max(b.cell_voltages) for b in d.values())
            - min(min(b.cell_voltages) for b in d.values()),
        ), serial, bmu_device),
        BmuInfoSensor(rt.status, "inverter", serial, bmu_device, lambda: rt.info.inverter,
                      lambda: {"application": rt.info.application, "phase": rt.info.phase}),
        BmuInfoSensor(rt.status, "bms_count", serial, bmu_device, lambda: rt.info.bms_count, None),
        BmuInfoSensor(rt.status, "pt_version", serial, bmu_device,
                      lambda: rt.status.data.pt_version if rt.status.data else None, None),
    ]

    for index in range(1, rt.info.bms_count + 1):
        device = bms_device_info(hass, entry, rt, index)
        entities += [BmsSensor(rt.details, desc, serial, index, device) for desc in BMS_SENSORS]
        entities += [
            BmsSensor(rt.details, BydSensorDescription(
                key=f"cell_{cell + 1:02d}_voltage", translation_key="cell_voltage",
                translation_placeholders={"cell": str(cell + 1)},
                native_unit_of_measurement=MV, device_class=SensorDeviceClass.VOLTAGE,
                state_class=M, value_fn=lambda b, c=cell: b.cell_voltages[c],
                attr_fn=lambda b, c=cell, i=index: {
                    "bms": i, "cell": c + 1, "module": "B1" if c < 8 else "B2"},
            ), serial, index, device)
            for cell in range(CELLS_PER_BMS)
        ]
        entities += [
            BmsSensor(rt.details, BydSensorDescription(
                key=f"temperature_{t + 1}", translation_key="cell_temperature",
                translation_placeholders={"sensor": str(t + 1)},
                native_unit_of_measurement=C, device_class=SensorDeviceClass.TEMPERATURE,
                state_class=M, value_fn=lambda b, i=t: b.temperatures[i],
                attr_fn=lambda b, t=t, i=index: {
                    "bms": i, "sensor": t + 1, "module": "B1" if t < 4 else "B2"},
            ), serial, index, device)
            for t in range(TEMPS_PER_BMS)
        ]
    async_add_entities(entities)


class BmuSensor(CoordinatorEntity, SensorEntity):
    """Sensor fed by the BMU status coordinator."""

    _attr_has_entity_name = True
    entity_description: BydSensorDescription

    def __init__(self, coordinator, description, serial, device) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = device

    @property
    def native_value(self):
        data: BmuStatus | None = self.coordinator.data
        return self.entity_description.value_fn(data) if data else None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        fn = self.entity_description.attr_fn
        return fn(data) if data and fn else None


class BmuInfoSensor(CoordinatorEntity, SensorEntity):
    """Static/diagnostic BMU information."""

    _attr_has_entity_name = True
    _attr_entity_category = DIAG

    def __init__(self, coordinator, key, serial, device, value, attrs) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_device_info = device
        self._value = value
        self._attrs = attrs

    @property
    def native_value(self):
        return self._value()

    @property
    def extra_state_attributes(self):
        return self._attrs() if self._attrs else None


class BmsSensor(CoordinatorEntity, SensorEntity):
    """Sensor fed by the BMS detail coordinator."""

    _attr_has_entity_name = True
    entity_description: BydSensorDescription

    def __init__(self, coordinator, description, serial, index, device) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._index = index
        self._attr_unique_id = f"{serial}_bms{index}_{description.key}"
        self._attr_device_info = device
        if description.translation_placeholders:
            self._attr_translation_placeholders = dict(description.translation_placeholders)

    @property
    def _bms(self) -> BmsData | None:
        return (self.coordinator.data or {}).get(self._index)

    @property
    def available(self) -> bool:
        return super().available and self._bms is not None

    @property
    def native_value(self):
        bms = self._bms
        return self.entity_description.value_fn(bms) if bms else None

    @property
    def extra_state_attributes(self):
        bms = self._bms
        fn = self.entity_description.attr_fn
        return fn(bms) if bms and fn else None
