"""Synchronous Modbus controller for AlphaESS inverters.

Pure Modbus logic, no Home Assistant dependencies — every public method is
blocking and meant to be called from HA via ``async_add_executor_job``.
"""
from __future__ import annotations

import logging
import time

from pymodbus.client import ModbusTcpClient

from .const import (
    POWER_OFFSET,
    REG_DISPATCH_BLOCK,
    REG_DISPATCH_START,
    REG_FEED_IN_LIMIT,
    REG_PV_SWITCH,
)

_LOGGER = logging.getLogger(__name__)


class AlphaessModbus:
    """Talk to an AlphaESS inverter over Modbus TCP."""

    def __init__(self, host: str, port: int, unit: int) -> None:
        self._host = host
        self._port = port
        self._unit = unit

    def _connect(self):
        client = ModbusTcpClient(self._host, port=self._port, timeout=6)
        return client if client.connect() else None

    def _write(self, client, address, values):
        """Write holding registers, compatible with pymodbus 3.x and older."""
        if not isinstance(values, list):
            values = [values]
        try:
            return client.write_registers(address, values, device_id=self._unit)
        except TypeError:
            return client.write_registers(address, values, slave=self._unit)

    def _power_word(self, mode: str, battery_power: int, soc, discharge_floor) -> int:
        """Encode the dispatch active-power setpoint for the given battery mode."""
        if mode == "discharge":
            if soc is None or soc < discharge_floor:
                return POWER_OFFSET  # blocked -> neutral
            return POWER_OFFSET + battery_power
        if mode == "charge":
            return max(0, POWER_OFFSET - battery_power)
        return POWER_OFFSET  # neutral = 0 W

    def pv_off(self, mode: str, battery_power: int, soc, discharge_floor) -> bool:
        """PV OFF (0x088A=2) + battery per ``mode``, via an active dispatch."""
        power = self._power_word(mode, battery_power, soc, discharge_floor)
        client = self._connect()
        if not client:
            _LOGGER.warning("Modbus connect failed (%s:%s)", self._host, self._port)
            return False
        try:
            # active(hi,lo) reactive(hi,lo) mode soc time(hi,lo) flow pvswitch(2=off)
            block = [0, power, 0, POWER_OFFSET, 2, 10, 0, 300, 0, 2]
            self._write(client, REG_DISPATCH_BLOCK, block)
            self._write(client, REG_DISPATCH_START, [1])  # PV switch only acts while active
            self._write(client, REG_PV_SWITCH, [2])       # re-assert PV OFF
            _LOGGER.debug("PV OFF applied, battery=%s power_word=%s", mode, power)
            return True
        finally:
            client.close()

    def dispatch_stop(self) -> bool:
        """Stop dispatch (0x0880=0) — the inverter restores PV automatically."""
        client = self._connect()
        if not client:
            return False
        try:
            self._write(client, REG_DISPATCH_START, [0])
            _LOGGER.debug("Dispatch stopped -> PV restored")
            return True
        finally:
            client.close()

    def set_feedin(self, percent: int) -> bool:
        """Set feed-in limit (0x0800). Stops dispatch first or the inverter ignores it."""
        percent = max(0, min(100, int(percent)))
        client = self._connect()
        if not client:
            _LOGGER.warning("Modbus connect failed (%s:%s)", self._host, self._port)
            return False
        try:
            self._write(client, REG_DISPATCH_START, [0])
            time.sleep(1)
            ok = not self._write(client, REG_FEED_IN_LIMIT, [percent]).isError()
            _LOGGER.debug("Feed-in limit -> %s%% (ok=%s)", percent, ok)
            return ok
        finally:
            client.close()
