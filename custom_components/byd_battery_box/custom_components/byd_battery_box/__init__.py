"""The BYD Battery-Box integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.helpers.start import async_at_started
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
from .health import HealthModel
from .protocol import BydClient, BydError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_CARD_FILE = Path(__file__).parent / "frontend" / "byd-battery-box-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card and make sure dashboards load it."""
    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(_CARD_FILE), False)]
    )
    url = f"{CARD_URL}?v={version}"

    async def _register(_hass: HomeAssistant) -> None:
        # 1) Dashboard resource (storage mode) - the reliable way, like HACS cards.
        if await _async_ensure_lovelace_resource(hass, url):
            return
        # 2) Fallback for YAML-mode dashboards: global frontend module.
        try:
            from homeassistant.components.frontend import add_extra_js_url

            add_extra_js_url(hass, url)
            _LOGGER.debug("Dashboard card added as frontend module: %s", url)
        except (ImportError, KeyError):
            _LOGGER.warning(
                "Could not register the dashboard card automatically. Add %s "
                "as a dashboard resource (JavaScript module)", CARD_URL
            )

    async_at_started(hass, _register)
    return True


async def _async_ensure_lovelace_resource(hass: HomeAssistant, url: str) -> bool:
    """Create or update our entry in the dashboard resources. False if not possible."""
    data = hass.data.get("lovelace")
    resources = data.get("resources") if isinstance(data, dict) else getattr(data, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return False  # YAML mode: resources are read-only
    try:
        if not getattr(resources, "loaded", True):
            await resources.async_load()
            resources.loaded = True
        for item in resources.async_items():
            if str(item.get("url", "")).split("?")[0] == CARD_URL:
                if item["url"] != url or item.get("type") != "module":
                    await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
                    _LOGGER.debug("Dashboard card resource updated to %s", url)
                return True
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Dashboard card registered as dashboard resource: %s", url)
    except Exception:  # noqa: BLE001 - never break the integration because of the card
        _LOGGER.exception("Registering the dashboard card resource failed")
        return False
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

    store: Store = Store(hass, 1, f"{DOMAIN}.health.{info.serial}")
    health = HealthModel(await store.async_load())
    last_seen: dict = {}

    @callback
    def _update_health() -> None:
        data = details.data
        if not details.last_update_success or not data or last_seen.get("data") is data:
            return
        last_seen["data"] = data
        health.update(dt_util.utcnow(), data)
        store.async_delay_save(lambda: health.state, 120)

    # Alarms are evaluated before the entities are refreshed (registered first).
    entry.async_on_unload(status.async_add_listener(callback(lambda: alarms.update_status(status.data))))
    entry.async_on_unload(details.async_add_listener(callback(lambda: alarms.update_bms(details.data))))
    entry.async_on_unload(details.async_add_listener(_update_health))
    entry.async_on_unload(alarms.clear_issues)

    await status.async_config_entry_first_refresh()
    await details.async_config_entry_first_refresh()
    alarms.update_status(status.data)
    alarms.update_bms(details.data)
    _update_health()

    entry.runtime_data = BydRuntimeData(client, info, status, details, alarms, health)
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
