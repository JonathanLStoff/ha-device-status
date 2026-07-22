DOMAIN = "ha_device_status"

# Top-level config keys
CONF_ITEMS = "items"
CONF_NOTIFY = "notify_offline"          # list of item names that should trigger a notification
CONF_NOTIFY_SERVICES = "notify_services"  # HA companion-app notify services (phones)
CONF_NOTIFY_ONLINE = "notify_online"    # also notify when a device recovers
CONF_CRON = "cron"                      # cron expression controlling how often to poll

# Per-item keys
CONF_NAME = "name"
CONF_TYPE = "type"
CONF_IP = "ip"
CONF_PORT = "port"
CONF_TOPIC = "topic"
CONF_PAYLOAD = "payload"                # optional expected payload for MQTT
CONF_INTERFACE = "interface"            # bind ping to an interface, e.g. a WireGuard tunnel (wg0)
CONF_COUNT = "count"                    # number of ping/port attempts
CONF_TIMEOUT = "timeout"               # per-attempt timeout in seconds

DEFAULT_PAYLOAD = "online"
DEFAULT_CRON = "*/1 * * * *"            # every minute
DEFAULT_COUNT = 2
DEFAULT_TIMEOUT = 3
