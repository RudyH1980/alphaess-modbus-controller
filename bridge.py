"""
AlphaESS Modbus Controller — negative-price PV control + zero-export

What it does (local Modbus TCP, no cloud needed for control):
  * Zero-export: cap feed-in to the grid (Modbus 0x0800).
  * Negative-price mode: when your dynamic electricity price drops below a
    threshold, switch the PV OFF (Modbus dispatch PV-switch 0x088A=2) so the
    house imports everything from the grid (you get paid to consume), and
    optionally hold/charge/discharge the battery. PV is restored automatically
    when the dispatch stops.

Key discovery: the AlphaESS "Dispatch PV Switch" (register 0x088A: 1=on, 2=off)
only takes effect while a dispatch is active (0x0880=1). The inverter restores
PV to normal as soon as the dispatch ends — a built-in safety net.

Tested on an AlphaESS SMILE (unit/slave id 85) over Modbus TCP port 502.

Everything is configured via environment variables — NO secrets in this file.
See compose.example.yml / README.md.
"""

import logging
import os
import signal
import time

import requests
from pymodbus.client import ModbusTcpClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Inverter (Modbus TCP) ──────────────────────────────────────────────────
ALPHAESS_HOST = os.getenv("ALPHAESS_HOST", "192.168.1.55")
ALPHAESS_PORT = int(os.getenv("ALPHAESS_PORT", "502"))
ALPHAESS_UNIT = int(os.getenv("ALPHAESS_UNIT", "85"))   # AlphaESS default slave id

# ── Home Assistant (to read price + battery sensors) ───────────────────────
HA_URL = os.getenv("HA_URL", "http://127.0.0.1:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")                    # long-lived token (required)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# Sensor with the live battery State-of-Charge (%) — used as a safety floor.
HA_SOC_SENSOR = os.getenv("HA_SOC_SENSOR", "")

# ── Zero-export (optional) ─────────────────────────────────────────────────
# Reads input_boolean.alphaess_zero_export when present; else this default.
DEFAULT_ZERO_EXPORT = os.getenv("DEFAULT_ZERO_EXPORT", "false").lower() == "true"

# ── Negative-price mode ────────────────────────────────────────────────────
NEG_PRICE_ENABLED = os.getenv("NEG_PRICE_ENABLED", "true").lower() == "true"
# Any HA sensor that reports the current electricity price (€/kWh): Frank Energie,
# Nordpool, EPEX, Tibber, ENTSO-e, ... Market/spot price is what goes negative.
NEG_PRICE_SENSOR = os.getenv("NEG_PRICE_SENSOR", "")
NEG_PRICE_THRESHOLD = float(os.getenv("NEG_PRICE_THRESHOLD", "0.0"))   # €/kWh
# Battery behaviour while in negative-price mode: neutral | charge | discharge
NEG_BATTERY_MODE = os.getenv("NEG_BATTERY_MODE", "neutral").lower()
NEG_BATTERY_POWER = int(os.getenv("NEG_BATTERY_POWER", "2000"))        # W (charge/discharge)
NEG_DISCHARGE_SOC_FLOOR = float(os.getenv("NEG_DISCHARGE_SOC_FLOOR", "15"))  # % min SOC to discharge

HA_HEADERS = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}

# AlphaESS dispatch registers (11 consecutive, 0x0880..0x088A)
REG_DISPATCH_START = 0x0880        # 1 = start, 0 = stop (PV restores on stop)
REG_DISPATCH_BLOCK = 0x0881        # active(2) reactive(2) mode soc time(2) flow pvswitch
REG_FEED_IN_LIMIT = 0x0800         # % of AC capacity (0 = no export)
REG_PV_SWITCH = 0x088A             # 1 = PV on, 2 = PV off, 0 = unchanged
POWER_OFFSET = 32000               # active power: <offset = charge, >offset = discharge


def ha_state(entity):
    """Return a HA entity state as float, or None."""
    if not entity:
        return None
    try:
        r = requests.get(f"{HA_URL}/api/states/{entity}", headers=HA_HEADERS, timeout=5)
        if r.status_code == 200:
            s = r.json().get("state")
            if s not in ("unavailable", "unknown", None, ""):
                return float(s)
    except Exception as e:
        log.warning("HA read %s failed: %s", entity, e)
    return None


def ha_bool(entity, default):
    """Return a HA input_boolean as bool, or default if absent/unreadable."""
    try:
        r = requests.get(f"{HA_URL}/api/states/{entity}", headers=HA_HEADERS, timeout=5)
        if r.status_code == 200:
            st = r.json().get("state")
            if st in ("on", "off"):
                return st == "on"
    except Exception:
        pass
    return default


def _connect():
    c = ModbusTcpClient(ALPHAESS_HOST, port=ALPHAESS_PORT, timeout=6)
    return c if c.connect() else None


def _write(client, address, values):
    """Write holding registers, compatible with pymodbus 3.x (device_id) and older (slave)."""
    if not isinstance(values, list):
        values = [values]
    try:
        return client.write_registers(address, values, device_id=ALPHAESS_UNIT)
    except TypeError:
        return client.write_registers(address, values, slave=ALPHAESS_UNIT)


def _active_power_word(mode):
    """Encode the dispatch active-power setpoint for the given battery mode."""
    if mode == "charge":
        return max(0, POWER_OFFSET - NEG_BATTERY_POWER)      # < offset = charge
    if mode == "discharge":
        return POWER_OFFSET + NEG_BATTERY_POWER              # > offset = discharge
    return POWER_OFFSET                                       # neutral = 0 W


def modbus_set_feedin(percent: int) -> bool:
    """Set feed-in limit (0x0800). Must stop dispatch first or the inverter ignores it."""
    percent = max(0, min(100, int(percent)))
    c = _connect()
    if not c:
        log.warning("Modbus connect failed (%s:%d)", ALPHAESS_HOST, ALPHAESS_PORT)
        return False
    try:
        _write(c, REG_DISPATCH_START, [0])
        time.sleep(1)
        ok = not _write(c, REG_FEED_IN_LIMIT, [percent]).isError()
        log.info("Feed-in limit -> %d%%", percent) if ok else log.warning("feed-in write failed")
        return ok
    finally:
        c.close()


def modbus_pv_off(soc, mode):
    """PV OFF (0x088A=2) + battery per `mode`, via an active dispatch."""
    if mode == "discharge" and (soc is None or soc < NEG_DISCHARGE_SOC_FLOOR):
        mode_note = f"discharge blocked (SOC {soc}% < floor {NEG_DISCHARGE_SOC_FLOOR}%) -> neutral"
        power = POWER_OFFSET
    else:
        mode_note = mode
        power = _active_power_word(mode)
    c = _connect()
    if not c:
        log.warning("Modbus connect failed (%s:%d)", ALPHAESS_HOST, ALPHAESS_PORT)
        return False
    try:
        # 0x0881..0x088A: active(hi,lo) reactive(hi,lo) mode soc time(hi,lo) flow pvswitch(2=off)
        block = [0, power, 0, POWER_OFFSET, 2, 10, 0, 300, 0, 2]
        _write(c, REG_DISPATCH_BLOCK, block)
        _write(c, REG_DISPATCH_START, [1])     # start dispatch (PV switch only acts while active)
        _write(c, REG_PV_SWITCH, [2])          # re-assert PV OFF
        log.info("NEG-PRICE mode applied: PV OFF, battery=%s", mode_note)
        return True
    finally:
        c.close()


def modbus_dispatch_stop():
    """Stop dispatch (0x0880=0) — the inverter restores PV automatically."""
    c = _connect()
    if not c:
        return False
    try:
        _write(c, REG_DISPATCH_START, [0])
        log.info("Dispatch stopped -> PV restored")
        return True
    finally:
        c.close()


def main():
    if not HA_TOKEN:
        log.error("HA_TOKEN missing — set it in the environment")
        raise SystemExit(1)

    log.info("AlphaESS Modbus Controller started")
    log.info("  Inverter %s:%d (unit %d)", ALPHAESS_HOST, ALPHAESS_PORT, ALPHAESS_UNIT)
    log.info("  Negative-price mode: %s (sensor=%s, threshold<%.4f, battery=%s)",
             "ON" if NEG_PRICE_ENABLED else "OFF", NEG_PRICE_SENSOR or "<unset>",
             NEG_PRICE_THRESHOLD, NEG_BATTERY_MODE)

    def shutdown(sig, frame):
        log.info("Stopping — restoring PV / dispatch off")
        modbus_dispatch_stop()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    prev_zero_export = None
    was_pv_off = False

    while True:
        soc = ha_state(HA_SOC_SENSOR)

        # PV-off is driven by Home Assistant: the manual/scheduled switch
        # (input_boolean.pv_shutdown_active, set by your planner automations) OR,
        # as a fallback for users without those automations, a negative price.
        pv_off_switch = ha_bool("input_boolean.pv_shutdown_active", False)
        price = ha_state(NEG_PRICE_SENSOR) if NEG_PRICE_ENABLED else None
        pv_off_price = price is not None and price < NEG_PRICE_THRESHOLD
        pv_off = pv_off_switch or pv_off_price

        # Battery while PV is off: charge from the grid if the negative-price-charge
        # switch is on (get paid to import + fill the battery), else the env default.
        grid_charge = ha_bool("input_boolean.alphaess_negative_price_charge", False)
        batt_mode = "charge" if grid_charge else NEG_BATTERY_MODE

        if pv_off:
            modbus_pv_off(soc, batt_mode)      # re-applied each cycle (keeps the dispatch alive)
            prev_zero_export = None            # re-apply zero-export once PV returns
            log.info("PV OFF (switch=%s price=%s) battery=%s SOC=%s%%",
                     pv_off_switch, f"{price:.4f}" if price is not None else "n/a", batt_mode, soc)
        else:
            if was_pv_off:
                modbus_dispatch_stop()         # PV restored
            zero_export = ha_bool("input_boolean.alphaess_zero_export", DEFAULT_ZERO_EXPORT)
            if zero_export != prev_zero_export:
                modbus_set_feedin(0 if zero_export else 100)
                prev_zero_export = zero_export
            log.info("normal | price=%s | zero_export=%s | SOC=%s%%",
                     f"{price:.4f}" if price is not None else "n/a", prev_zero_export, soc)

        was_pv_off = pv_off
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
