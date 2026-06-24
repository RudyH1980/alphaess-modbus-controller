"""Coordinator that runs the control loop on every poll interval."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
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
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_PRICE_THRESHOLD,
    DEFAULT_UNIT,
    DOMAIN,
    SWITCH_NEG_CHARGE,
    SWITCH_PV_SHUTDOWN,
    SWITCH_ZERO_EXPORT,
)
from .controller import AlphaessModbus

_LOGGER = logging.getLogger(__name__)


class AlphaessCoordinator(DataUpdateCoordinator):
    """Drive the inverter from HA state on a fixed interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        opts = {**entry.data, **entry.options}

        self.modbus = AlphaessModbus(
            opts[CONF_HOST],
            int(opts.get(CONF_PORT, DEFAULT_PORT)),
            int(opts.get(CONF_UNIT, DEFAULT_UNIT)),
        )
        self.soc_sensor = opts.get(CONF_SOC_SENSOR)
        self.price_sensor = opts.get(CONF_PRICE_SENSOR)
        self.price_threshold = float(opts.get(CONF_PRICE_THRESHOLD, DEFAULT_PRICE_THRESHOLD))
        self.battery_mode = opts.get(CONF_BATTERY_MODE, DEFAULT_BATTERY_MODE)
        self.battery_power = int(opts.get(CONF_BATTERY_POWER, DEFAULT_BATTERY_POWER))
        self.discharge_floor = float(
            opts.get(CONF_DISCHARGE_SOC_FLOOR, DEFAULT_DISCHARGE_SOC_FLOOR)
        )

        # Desired control state, set by the switch entities.
        self.switch_state = {
            SWITCH_PV_SHUTDOWN: False,
            SWITCH_NEG_CHARGE: False,
            SWITCH_ZERO_EXPORT: False,
        }
        self._was_pv_off = False
        self._prev_zero_export = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=int(opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
            ),
        )

    def _read_float(self, entity):
        if not entity:
            return None
        state = self.hass.states.get(entity)
        if state and state.state not in ("unknown", "unavailable", None, ""):
            try:
                return float(state.state)
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_switch(self, key: str, value: bool) -> None:
        """Called by a switch entity; re-evaluate immediately."""
        self.switch_state[key] = value
        await self.async_request_refresh()

    async def _async_update_data(self):
        soc = self._read_float(self.soc_sensor)
        price = self._read_float(self.price_sensor)

        pv_off_switch = self.switch_state[SWITCH_PV_SHUTDOWN]
        pv_off_price = price is not None and price < self.price_threshold
        pv_off = pv_off_switch or pv_off_price

        grid_charge = self.switch_state[SWITCH_NEG_CHARGE]
        mode = "charge" if grid_charge else self.battery_mode

        if pv_off:
            await self.hass.async_add_executor_job(
                self.modbus.pv_off, mode, self.battery_power, soc, self.discharge_floor
            )
            self._prev_zero_export = None  # re-apply zero-export once PV returns
            status = {
                "mode": "pv_off",
                "pv": "off",
                "battery": mode,
                "trigger": "switch" if pv_off_switch else "price",
                "price": price,
                "soc": soc,
            }
        else:
            if self._was_pv_off:
                await self.hass.async_add_executor_job(self.modbus.dispatch_stop)
            zero = self.switch_state[SWITCH_ZERO_EXPORT]
            if zero != self._prev_zero_export:
                await self.hass.async_add_executor_job(
                    self.modbus.set_feedin, 0 if zero else 100
                )
                self._prev_zero_export = zero
            status = {
                "mode": "zero_export" if zero else "normal",
                "pv": "on",
                "battery": "self_consumption",
                "trigger": "none",
                "price": price,
                "soc": soc,
            }

        self._was_pv_off = pv_off
        _LOGGER.debug("cycle: %s", status)
        return status
