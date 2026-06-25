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
    REG_BATTERY_POWER,
    REG_BATTERY_SOC,
    REG_DISPATCH_BLOCK,
    REG_DISPATCH_START,
    REG_FEED_IN_LIMIT,
    REG_GRID_L1,
    REG_GRID_L2,
    REG_GRID_L3,
    REG_GRID_TOTAL,
    REG_PPV1,
    REG_PPV2,
    REG_PPV3,
    REG_PPV4,
    REG_PPV_TOTAL,
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
        # The AlphaESS inverter accepts only one Modbus TCP client at a time, so
        # the cloud integration can briefly hold the slot. Retry a couple of times
        # with a short backoff before giving up.
        for attempt in range(3):
            client = ModbusTcpClient(self._host, port=self._port, timeout=6)
            if client.connect():
                return client
            client.close()
            if attempt < 2:
                time.sleep(1)
        return None

    def _write(self, client, address, values):
        """Write holding registers, compatible with pymodbus 3.x and older."""
        if not isinstance(values, list):
            values = [values]
        try:
            return client.write_registers(address, values, device_id=self._unit)
        except TypeError:
            return client.write_registers(address, values, slave=self._unit)

    def _read(self, client, address, count):
        """Read holding registers, compatible with pymodbus 3.x and older."""
        try:
            return client.read_holding_registers(
                address, count=count, device_id=self._unit
            )
        except TypeError:
            return client.read_holding_registers(address, count, slave=self._unit)

    @staticmethod
    def _u32(regs, i):
        """Big-endian (high word first) unsigned 32-bit from a register list."""
        return (regs[i] << 16) | regs[i + 1]

    @staticmethod
    def _s32(regs, i):
        """Big-endian (high word first) signed 32-bit."""
        v = (regs[i] << 16) | regs[i + 1]
        return v - (1 << 32) if v >= (1 << 31) else v

    @staticmethod
    def _s16(v):
        return v - (1 << 16) if v >= (1 << 15) else v

    def read_measurements(self) -> dict | None:
        """Read all verified measurement registers in one connection.

        Returns a dict of physical quantities (W / %), or ``None`` if the
        inverter could not be reached. Read-only; never writes.
        """
        client = self._connect()
        if not client:
            _LOGGER.debug("Modbus connect failed for read (%s:%s)", self._host, self._port)
            return None
        try:
            grid = self._read(client, REG_GRID_L1, 0x0C)  # 0x001B..0x0026 covers L1/L2/L3/total
            batt = self._read(client, REG_BATTERY_SOC, 0x28)  # 0x0102..0x0129 covers SOC + power
            ppv_t = self._read(client, REG_PPV_TOTAL, 2)
            ppv1 = self._read(client, REG_PPV1, 2)
            ppv2 = self._read(client, REG_PPV2, 2)
            ppv3 = self._read(client, REG_PPV3, 2)
            ppv4 = self._read(client, REG_PPV4, 2)

            for r in (grid, batt, ppv_t, ppv1, ppv2, ppv3, ppv4):
                if r is None or r.isError():
                    _LOGGER.warning("Modbus measurement read returned an error")
                    return None

            gbase = REG_GRID_L1
            grid_l1 = self._s32(grid.registers, REG_GRID_L1 - gbase)
            grid_l2 = self._s32(grid.registers, REG_GRID_L2 - gbase)
            grid_l3 = self._s32(grid.registers, REG_GRID_L3 - gbase)
            grid_total = self._s32(grid.registers, REG_GRID_TOTAL - gbase)

            bbase = REG_BATTERY_SOC
            soc = round(self._s16(batt.registers[REG_BATTERY_SOC - bbase]) * 0.1, 1)
            battery_power = self._s16(batt.registers[REG_BATTERY_POWER - bbase])

            pv_total = self._u32(ppv_t.registers, 0)
            pv1 = self._u32(ppv1.registers, 0)
            pv2 = self._u32(ppv2.registers, 0)
            pv3 = self._u32(ppv3.registers, 0)
            pv4 = self._u32(ppv4.registers, 0)

            # House load via the energy balance (no reliable direct register):
            #   load = PV + grid_total + battery_power
            # with sign convention grid_total + = import, battery_power + = discharge.
            load = pv_total + grid_total + battery_power

            data = {
                "pv_total": pv_total,
                "pv1": pv1,
                "pv2": pv2,
                "pv3": pv3,
                "pv4": pv4,
                "grid_l1": grid_l1,
                "grid_l2": grid_l2,
                "grid_l3": grid_l3,
                "grid_total": grid_total,
                "battery_power": battery_power,
                "battery_soc": soc,
                "load": load,
            }
            _LOGGER.debug("measurements: %s", data)
            return data
        finally:
            client.close()

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
