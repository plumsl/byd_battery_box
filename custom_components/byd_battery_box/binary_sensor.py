"""Alarm binary sensors (device class problem)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .alarms import BMS_ALARMS, BMU_ALARMS, AlarmManager
from .coordinator import BydConfigEntry
from .sensor import bms_device_info, bmu_device_info


async def async_setup_entry(hass: HomeAssistant, entry: BydConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    rt = entry.runtime_data
    serial = rt.info.serial
    bmu = bmu_device_info(rt.info)
    entities: list[AlarmSensor] = [
        AlarmSensor(rt.details if key == "soc_imbalance" else rt.status, rt.alarms, 0, key,
                    f"{serial}_{key}", bmu)
        for key in BMU_ALARMS
    ]
    for index in range(1, rt.info.bms_count + 1):
        device = bms_device_info(hass, entry, rt, index)
        entities += [
            AlarmSensor(rt.details, rt.alarms, index, key, f"{serial}_bms{index}_{key}", device)
            for key in BMS_ALARMS
        ]
    async_add_entities(entities)


class AlarmSensor(CoordinatorEntity, BinarySensorEntity):
    """On = problem."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, alarms: AlarmManager, index: int, key: str,
                 unique_id: str, device) -> None:
        super().__init__(coordinator)
        self._alarms = alarms
        self._index = index
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = unique_id
        self._attr_device_info = device

    @property
    def is_on(self) -> bool:
        return self._alarms.get(self._index, self._key).active

    @property
    def extra_state_attributes(self):
        return self._alarms.get(self._index, self._key).details or None
