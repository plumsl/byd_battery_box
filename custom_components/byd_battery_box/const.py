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
