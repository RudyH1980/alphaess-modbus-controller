"""Coordinator that runs the control loop on every poll interval."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
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
    HELPER_GRID_CHARGE_POWER,
    HELPER_TARGET_SOC,
    HELPER_DISCHARGE_FLOOR,
    HELPER_DISCHARGE_POWER,
    SWITCH_GRID_CHARGE,
    SWITCH_GRID_DISCHARGE,
    SWITCH_PV_GUARD,
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
            SWITCH_PV_GUARD: True,  # default aan: PV moet altijd doorlopen (Rudy 2026-09-07)
            SWITCH_GRID_CHARGE: False,
            SWITCH_GRID_DISCHARGE: False,
        }
        self._was_grid_charge = False
        self._was_grid_discharge = False
        self._guard_stops = 0
        self._guard_last = None
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
        # Read all measurements locally over Modbus first. SOC for the control
        # logic now comes from the inverter itself; the optional cloud SOC
        # sensor is only a fallback if the Modbus read fails.
        measurements = await self.hass.async_add_executor_job(
            self.modbus.read_measurements
        )
        if measurements and measurements.get("battery_soc") is not None:
            soc = float(measurements["battery_soc"])
        else:
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
            # Feed-in eerst (set_feedin stopt dispatch), daarna pas grid-charge dispatch.
            zero = self.switch_state[SWITCH_ZERO_EXPORT]
            if zero != self._prev_zero_export:
                await self.hass.async_add_executor_job(
                    self.modbus.set_feedin, 0 if zero else 100
                )
                self._prev_zero_export = zero
            grid_charge_on = self.switch_state[SWITCH_GRID_CHARGE]
            discharge_on = self.switch_state[SWITCH_GRID_DISCHARGE] and not grid_charge_on
            if discharge_on:
                # Prijspiek: accu levert aan huis en net. PV blijft aan.
                dp = self._read_float(HELPER_DISCHARGE_POWER) or float(self.battery_power)
                floor = self._read_float(HELPER_DISCHARGE_FLOOR)
                if floor is None:
                    floor = self.discharge_floor
                await self.hass.async_add_executor_job(
                    self.modbus.grid_discharge, int(dp), soc, floor
                )
            elif self._was_grid_discharge:
                await self.hass.async_add_executor_job(self.modbus.dispatch_stop)
                _LOGGER.info("Ontladen naar net gestopt -> self-consumption")
            self._was_grid_discharge = discharge_on
            if grid_charge_on:
                # Lokaal uit net laden, PV blijft aan. Elke poll opnieuw (dispatch-duur 300 s).
                power = self._read_float(HELPER_GRID_CHARGE_POWER) or float(self.battery_power)
                target = self._read_float(HELPER_TARGET_SOC) or 100.0
                await self.hass.async_add_executor_job(
                    self.modbus.grid_charge, int(power), target
                )
            elif self._was_grid_charge:
                await self.hass.async_add_executor_job(self.modbus.dispatch_stop)
                _LOGGER.info("Grid charge gestopt -> self-consumption")
            self._was_grid_charge = grid_charge_on
            # Bewaking: ELKE dispatch die niet van ons is (cloud/VPP/app stuurt die per
            # kwartier: PV uit, 10 kW laden, of 8 kW ontladen naar net) direct stoppen.
            # Wij sturen zelf alleen via pv_off of grid_charge, en dan komen we hier niet.
            if (
                not grid_charge_on
                and not discharge_on
                and self.switch_state[SWITCH_PV_GUARD]
                and measurements
                and measurements.get("dispatch_active") == 1
            ):
                ok = await self.hass.async_add_executor_job(self.modbus.dispatch_stop)
                self._guard_stops += 1
                self._guard_last = dt_util.now().isoformat(timespec="seconds")
                _LOGGER.warning(
                    "PV-bewaking: vreemde dispatch gestopt (PV-switch=%s, power=%s W, mode=%s, ok=%s)",
                    measurements.get("dispatch_pv_switch"),
                    measurements.get("dispatch_power"),
                    measurements.get("dispatch_mode"),
                    ok,
                )
            status = {
                "mode": "grid_charge" if grid_charge_on else ("grid_discharge" if discharge_on else ("zero_export" if zero else "normal")),
                "pv": "on",
                "battery": "grid_charge" if grid_charge_on else ("discharge_to_grid" if discharge_on else "self_consumption"),
                "trigger": "none",
                "price": price,
                "soc": soc,
                "pv_guard": self.switch_state[SWITCH_PV_GUARD],
                "pv_guard_stops": self._guard_stops,
                "pv_guard_last_stop": self._guard_last,
            }

        self._was_pv_off = pv_off
        if measurements:
            status["measurements"] = measurements
            status["soc_source"] = "modbus"
        else:
            status["soc_source"] = "cloud" if self.soc_sensor else "none"
        _LOGGER.debug("cycle: %s", status)
        return status
