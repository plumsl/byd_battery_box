"""Config flow for the BYD Battery-Box."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    ALARM_OPTIONS,
    CONF_SOC_DIFF,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_DETAIL_INTERVAL,
    CONF_STATUS_INTERVAL,
    DEFAULT_DETAIL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    MAX_DETAIL_INTERVAL,
    SPREAD_FULL_SOC,
    MAX_STATUS_INTERVAL,
    MIN_DETAIL_INTERVAL,
    MIN_STATUS_INTERVAL,
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

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_alarms()

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_STATUS_INTERVAL,
                    default=opts.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
                ): vol.All(
                    _seconds(MIN_STATUS_INTERVAL, MAX_STATUS_INTERVAL, 5),
                    vol.Coerce(int),
                    vol.Range(MIN_STATUS_INTERVAL, MAX_STATUS_INTERVAL),
                ),
                vol.Required(
                    CONF_DETAIL_INTERVAL,
                    default=opts.get(CONF_DETAIL_INTERVAL, DEFAULT_DETAIL_INTERVAL),
                ): vol.All(
                    _seconds(MIN_DETAIL_INTERVAL, MAX_DETAIL_INTERVAL, 30),
                    vol.Coerce(int),
                    vol.Range(MIN_DETAIL_INTERVAL, MAX_DETAIL_INTERVAL),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_alarms(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update({k: int(v) for k, v in user_input.items()})
            return self.async_create_entry(data=self._data)

        opts = self.config_entry.options
        units = {CONF_TEMP_HIGH: "°C", CONF_TEMP_LOW: "°C", CONF_SOC_DIFF: "%"}
        schema = vol.Schema(
            {
                vol.Required(key, default=opts.get(key, default)): vol.All(
                    NumberSelector(NumberSelectorConfig(
                        min=lo, max=hi, step=step, mode=NumberSelectorMode.BOX,
                        unit_of_measurement=units.get(key, "mV"),
                    )),
                    vol.Coerce(int),
                    vol.Range(lo, hi),
                )
                for key, (default, lo, hi, step) in ALARM_OPTIONS.items()
            }
        )
        return self.async_show_form(
            step_id="alarms", data_schema=schema,
            description_placeholders={"full_soc": str(SPREAD_FULL_SOC)},
        )


def _seconds(minimum: int, maximum: int, step: int) -> NumberSelector:
    """Number field in seconds with hard limits."""
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=maximum, step=step,
            unit_of_measurement="s", mode=NumberSelectorMode.BOX,
        )
    )
