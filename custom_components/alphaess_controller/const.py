"""Constants for the AlphaESS Modbus Controller integration."""

DOMAIN = "alphaess_controller"
PLATFORMS = ["switch", "sensor"]

# Config keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT = "unit"
CONF_SOC_SENSOR = "soc_sensor"
CONF_PRICE_SENSOR = "price_sensor"
CONF_PRICE_THRESHOLD = "price_threshold"
CONF_BATTERY_MODE = "battery_mode"
CONF_BATTERY_POWER = "battery_power"
CONF_DISCHARGE_SOC_FLOOR = "discharge_soc_floor"
CONF_POLL_INTERVAL = "poll_interval"

# Defaults
DEFAULT_HOST = "192.168.1.55"
DEFAULT_PORT = 502
DEFAULT_UNIT = 85
DEFAULT_PRICE_THRESHOLD = 0.0
DEFAULT_BATTERY_MODE = "neutral"
DEFAULT_BATTERY_POWER = 2000
DEFAULT_DISCHARGE_SOC_FLOOR = 15.0
DEFAULT_POLL_INTERVAL = 60

BATTERY_MODES = ["neutral", "charge", "discharge"]

# AlphaESS dispatch registers (0x0880..0x088A) + feed-in limit
REG_DISPATCH_START = 0x0880   # 1 = start, 0 = stop (PV restores on stop)
REG_DISPATCH_BLOCK = 0x0881   # active(2) reactive(2) mode soc time(2) flow pvswitch
REG_FEED_IN_LIMIT = 0x0800    # % of AC capacity (0 = no export)
REG_PV_SWITCH = 0x088A        # 1 = PV on, 2 = PV off
POWER_OFFSET = 32000          # active power: <offset = charge, >offset = discharge

# Switch keys (also used as translation keys)
SWITCH_PV_SHUTDOWN = "pv_shutdown"
SWITCH_NEG_CHARGE = "negative_price_charge"
SWITCH_ZERO_EXPORT = "zero_export"

# --- Measurement (read-only) holding registers, verified vs cloud 2026-06-25 ---
# All read via function-code 3 (holding registers), 32-bit big-endian (high word
# first). Power in W. Sign convention noted per register. Each value matched the
# AlphaESS cloud sensors within a few % at a 0.1 s sampling offset.
REG_PPV_TOTAL = 0x0453      # uint32, total PV power (W)
REG_PPV1 = 0x041F           # uint32, PV string 1 power (W)
REG_PPV2 = 0x0423           # uint32, PV string 2 power (W)
REG_PPV3 = 0x0427           # uint32, PV string 3 power (W)
REG_PPV4 = 0x042B           # uint32, PV string 4 power (W)
REG_GRID_L1 = 0x001B        # int32, grid power L1 (W; + = import, - = export)
REG_GRID_L2 = 0x001D        # int32, grid power L2 (W; + = import, - = export)
REG_GRID_L3 = 0x001F        # int32, grid power L3 (W; + = import, - = export)
REG_GRID_TOTAL = 0x0021     # int32, grid power total (W; + = import, - = export)
REG_BATTERY_SOC = 0x0102    # int16, battery SOC, scale 0.1 -> %
REG_BATTERY_POWER = 0x0126  # int16, battery power (W; - = charging, + = discharging)
