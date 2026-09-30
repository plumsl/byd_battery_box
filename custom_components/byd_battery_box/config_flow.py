"""Config flow for the BYD Battery-Box."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_DETAIL_INTERVAL,
    CONF_STATUS_INTERVAL,
    DEFAULT_DETAIL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
)
from .protocol import BydClient, BydConnectionError, BydError


class BydConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = BydClient(user_input[CONF_HOST], user_input[CONF_PORT])
            try:
                info = await client.read_info()
            except BydConnectionError:
                errors["base"] = "cannot_connect"
            except BydError:
                errors["base"] = "invalid_response"
            else:
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(
                    title=f"BYD Battery-Box {info.battery_type}", data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(1, 65535)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BydOptionsFlow()


class BydOptionsFlow(OptionsFlow):
    """Polling intervals."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_STATUS_INTERVAL,
                    default=opts.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
                ): vol.All(int, vol.Range(10, 600)),
                vol.Required(
                    CONF_DETAIL_INTERVAL,
                    default=opts.get(CONF_DETAIL_INTERVAL, DEFAULT_DETAIL_INTERVAL),
                ): vol.All(int, vol.Range(60, 3600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
