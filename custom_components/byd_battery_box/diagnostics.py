"""Diagnostics download: parsed values plus the raw frames of the last cycles."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import BydConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: BydConfigEntry) -> dict[str, Any]:
    rt = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_HOST}),
        "options": dict(entry.options),
        "bmu_info": asdict(rt.info),
        "bmu_status": asdict(rt.status.data) if rt.status.data else None,
        "bms": {k: asdict(v) for k, v in (rt.details.data or {}).items()},
        "raw_frames": rt.client.last_frames,
    }
