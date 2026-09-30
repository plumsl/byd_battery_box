"""The BYD Battery-Box integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_DETAIL_INTERVAL,
    CONF_STATUS_INTERVAL,
    DEFAULT_DETAIL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_STATUS_INTERVAL,
    MAX_DETAIL_INTERVAL,
    MAX_STATUS_INTERVAL,
    MIN_DETAIL_INTERVAL,
    MIN_STATUS_INTERVAL,
)
from .coordinator import BydConfigEntry, BydRuntimeData, DetailCoordinator, StatusCoordinator
from .protocol import BydClient, BydError

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BydConfigEntry) -> bool:
    """Set up the battery from a config entry."""
    client = BydClient(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    try:
        info = await client.read_info()
    except BydError as err:
        raise ConfigEntryNotReady(str(err)) from err

    status = StatusCoordinator(
        hass, entry, client,
        _clamp(entry.options.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
               MIN_STATUS_INTERVAL, MAX_STATUS_INTERVAL),
    )
    details = DetailCoordinator(
        hass, entry, client,
        _clamp(entry.options.get(CONF_DETAIL_INTERVAL, DEFAULT_DETAIL_INTERVAL),
               MIN_DETAIL_INTERVAL, MAX_DETAIL_INTERVAL),
        info.bms_count,
    )
    await status.async_config_entry_first_refresh()
    await details.async_config_entry_first_refresh()

    entry.runtime_data = BydRuntimeData(client, info, status, details)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BydConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: BydConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _clamp(value: float, minimum: int, maximum: int) -> int:
    """Enforce the limits even for values stored by older versions."""
    return int(min(max(value, minimum), maximum))
