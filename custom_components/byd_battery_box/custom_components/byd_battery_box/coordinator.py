"""Data update coordinators for the BYD Battery-Box."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .alarms import AlarmManager
from .health import HealthModel
from .protocol import BmsData, BmuInfo, BmuStatus, BydClient, BydError

_LOGGER = logging.getLogger(__name__)


@dataclass
class BydRuntimeData:
    """Objects stored in entry.runtime_data."""

    client: BydClient
    info: BmuInfo
    status: "StatusCoordinator"
    details: "DetailCoordinator"
    alarms: "AlarmManager"
    health: "HealthModel"


type BydConfigEntry = ConfigEntry[BydRuntimeData]


class StatusCoordinator(DataUpdateCoordinator[BmuStatus]):
    """Fast polling of the BMU overview (one small request)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: BydClient, seconds: int) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name="BYD BMU status",
            update_interval=timedelta(seconds=seconds),
        )
        self.client = client

    async def _async_update_data(self) -> BmuStatus:
        try:
            return await self.client.read_status()
        except BydError as err:
            raise UpdateFailed(str(err)) from err


class DetailCoordinator(DataUpdateCoordinator[dict[int, BmsData]]):
    """Slow polling of all BMS (cell voltages, temperatures, ...)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: BydClient,
                 seconds: int, bms_count: int) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name="BYD BMS details",
            update_interval=timedelta(seconds=seconds),
        )
        self.client = client
        self.bms_count = bms_count
        self.info: BmuInfo | None = None

    async def _async_update_data(self) -> dict[int, BmsData]:
        try:
            self.info, data = await self.client.read_details(self.bms_count)
        except BydError as err:
            raise UpdateFailed(str(err)) from err
        return data
