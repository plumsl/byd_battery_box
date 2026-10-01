"""The BYD Battery-Box integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .alarms import AlarmManager
from .const import (
    CARD_URL,
    CONF_DETAIL_INTERVAL,
    CONF_STATUS_INTERVAL,
    DEFAULT_DETAIL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    MAX_DETAIL_INTERVAL,
    MAX_STATUS_INTERVAL,
    MIN_DETAIL_INTERVAL,
    MIN_STATUS_INTERVAL,
)
from .coordinator import BydConfigEntry, BydRuntimeData, DetailCoordinator, StatusCoordinator
from .protocol import BydClient, BydError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_CARD_FILE = Path(__file__).parent / "frontend" / "byd-battery-box-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card and load it on every dashboard."""
    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(_CARD_FILE), False)]
    )
    url = f"{CARD_URL}?v={version}"

    @callback
    def _register(_event=None) -> bool:
        try:
            from homeassistant.components.frontend import add_extra_js_url

            add_extra_js_url(hass, url)
        except (ImportError, KeyError):
            return False
        _LOGGER.debug("Dashboard card registered: %s", url)
        return True

    # The frontend may not be ready yet when this integration loads early.
    if not _register():
        _LOGGER.debug("Frontend not ready, registering the card after start")

        @callback
        def _late(_event) -> None:
            if not _register():
                _LOGGER.warning(
                    "Could not register the dashboard card automatically. Add %s "
                    "as a dashboard resource (JavaScript module) instead", CARD_URL
                )

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _late)
    return True


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
    alarms = AlarmManager(hass, entry.entry_id, info.serial, dict(entry.options), info.bms_count)

    # Alarms are evaluated before the entities are refreshed (registered first).
    entry.async_on_unload(status.async_add_listener(callback(lambda: alarms.update_status(status.data))))
    entry.async_on_unload(details.async_add_listener(callback(lambda: alarms.update_bms(details.data))))
    entry.async_on_unload(alarms.clear_issues)

    await status.async_config_entry_first_refresh()
    await details.async_config_entry_first_refresh()
    alarms.update_status(status.data)
    alarms.update_bms(details.data)

    entry.runtime_data = BydRuntimeData(client, info, status, details, alarms)
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
