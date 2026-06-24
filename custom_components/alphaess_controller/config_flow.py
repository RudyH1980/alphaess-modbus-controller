"""Config + options flow for the AlphaESS Modbus Controller."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    BATTERY_MODES,
    CONF_BATTERY_MODE,
    CONF_BATTERY_POWER,
    CONF_DISCHARGE_SOC_FLOOR,
    CONF_HOST,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_PRICE_SENSOR,
    CONF_PRICE_THRESHOLD,
    CONF_SOC_SENSOR,
    CONF_UNIT,
    DEFAULT_BATTERY_MODE,
    DEFAULT_BATTERY_POWER,
    DEFAULT_DISCHARGE_SOC_FLOOR,
    DEFAULT_HOST,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_PRICE_THRESHOLD,
    DEFAULT_UNIT,
    DOMAIN,
)

_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)
_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=BATTERY_MODES, mode=selector.SelectSelectorMode.DROPDOWN
    )
)


class AlphaessConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Initial setup via the UI."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="AlphaESS Modbus Controller", data=user_input
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_UNIT, default=DEFAULT_UNIT): int,
                vol.Optional(CONF_SOC_SENSOR): _SENSOR_SELECTOR,
                vol.Optional(CONF_PRICE_SENSOR): _SENSOR_SELECTOR,
                vol.Required(
                    CONF_PRICE_THRESHOLD, default=DEFAULT_PRICE_THRESHOLD
                ): vol.Coerce(float),
                vol.Required(
                    CONF_BATTERY_MODE, default=DEFAULT_BATTERY_MODE
                ): _MODE_SELECTOR,
                vol.Required(CONF_BATTERY_POWER, default=DEFAULT_BATTERY_POWER): int,
                vol.Required(
                    CONF_DISCHARGE_SOC_FLOOR, default=DEFAULT_DISCHARGE_SOC_FLOOR
                ): vol.Coerce(float),
                vol.Required(
                    CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                ): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    def async_get_options_flow(config_entry):
        return AlphaessOptionsFlow(config_entry)


class AlphaessOptionsFlow(config_entries.OptionsFlow):
    """Tune thresholds without re-adding the integration."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        cur = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PRICE_SENSOR, default=cur.get(CONF_PRICE_SENSOR, "")
                ): _SENSOR_SELECTOR,
                vol.Optional(
                    CONF_SOC_SENSOR, default=cur.get(CONF_SOC_SENSOR, "")
                ): _SENSOR_SELECTOR,
                vol.Required(
                    CONF_PRICE_THRESHOLD,
                    default=cur.get(CONF_PRICE_THRESHOLD, DEFAULT_PRICE_THRESHOLD),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_BATTERY_MODE,
                    default=cur.get(CONF_BATTERY_MODE, DEFAULT_BATTERY_MODE),
                ): _MODE_SELECTOR,
                vol.Required(
                    CONF_BATTERY_POWER,
                    default=cur.get(CONF_BATTERY_POWER, DEFAULT_BATTERY_POWER),
                ): int,
                vol.Required(
                    CONF_DISCHARGE_SOC_FLOOR,
                    default=cur.get(
                        CONF_DISCHARGE_SOC_FLOOR, DEFAULT_DISCHARGE_SOC_FLOOR
                    ),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=cur.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
