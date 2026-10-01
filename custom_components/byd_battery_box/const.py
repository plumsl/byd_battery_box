"""Constants for the BYD Battery-Box integration."""

DOMAIN = "byd_battery_box"
MANUFACTURER = "BYD"

DEFAULT_PORT = 8080
CONF_STATUS_INTERVAL = "status_interval"
CONF_DETAIL_INTERVAL = "detail_interval"
DEFAULT_STATUS_INTERVAL = 30
DEFAULT_DETAIL_INTERVAL = 300

# Limits. The BMU overview is one small request; below 10 s it only adds load,
# because the BMU itself updates its values with a delay.
MIN_STATUS_INTERVAL = 10
MAX_STATUS_INTERVAL = 600
# A detail cycle takes about 4.5 s per BMS and blocks the connection meanwhile
# (Be Connect cannot connect during that time). 60 s keeps enough headroom.
MIN_DETAIL_INTERVAL = 60
MAX_DETAIL_INTERVAL = 3600

# Nominal usable energy of one LVL 15.4 (one BMS)
NOMINAL_KWH_PER_BMS = 15.36

# Alarm thresholds (options)
CONF_CELL_HIGH = "cell_voltage_high"
CONF_CELL_LOW = "cell_voltage_low"
CONF_SPREAD = "cell_spread"
CONF_SPREAD_FULL = "cell_spread_full"
CONF_TEMP_HIGH = "temperature_high"
CONF_TEMP_LOW = "temperature_low"
CONF_SOC_DIFF = "soc_imbalance"

# key: (default, min, max, step)
ALARM_OPTIONS = {
    CONF_CELL_HIGH: (3600, 3400, 3700, 10),
    CONF_CELL_LOW: (2900, 2500, 3200, 10),
    CONF_SPREAD: (50, 10, 300, 5),
    CONF_SPREAD_FULL: (150, 20, 400, 5),
    CONF_TEMP_HIGH: (45, 30, 60, 1),
    CONF_TEMP_LOW: (5, -10, 20, 1),
    CONF_SOC_DIFF: (10, 2, 50, 1),
}
# Above this SOC the "full" spread threshold applies (LFP diverges at the top)
SPREAD_FULL_SOC = 95

CARD_URL = "/byd_battery_box/byd-battery-box-card.js"
