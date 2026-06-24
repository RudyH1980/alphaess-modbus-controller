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
