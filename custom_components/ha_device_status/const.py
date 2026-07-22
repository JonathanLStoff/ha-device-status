DOMAIN = "ha_device_status"

# Top-level config keys
CONF_ITEMS = "items"
CONF_NOTIFY = "notify_offline"          # list of item names that should trigger a notification
CONF_NOTIFY_SERVICES = "notify_services"  # HA companion-app notify services (phones)
CONF_NOTIFY_ONLINE = "notify_online"    # also notify when a device recovers
CONF_CRON = "cron"                      # cron expression controlling how often to poll
CONF_WIREGUARD = "wireguard"            # optional WireGuard interface to set up

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

# WireGuard config keys
CONF_WG_INTERFACE = "interface"
CONF_WG_CONFIG_PATH = "config_path"      # path to an existing wg-quick style .conf
CONF_WG_PRIVATE_KEY = "private_key"      # used when building the conf inline instead
CONF_WG_ADDRESS = "address"
CONF_WG_LISTEN_PORT = "listen_port"
CONF_WG_DNS = "dns"
CONF_WG_PEERS = "peers"
CONF_WG_PEER_PUBLIC_KEY = "public_key"
CONF_WG_PEER_PRESHARED_KEY = "preshared_key"
CONF_WG_PEER_ENDPOINT = "endpoint"
CONF_WG_PEER_ALLOWED_IPS = "allowed_ips"
CONF_WG_PEER_PERSISTENT_KEEPALIVE = "persistent_keepalive"

DEFAULT_PAYLOAD = "online"
DEFAULT_CRON = "*/1 * * * *"            # every minute
DEFAULT_COUNT = 2
DEFAULT_TIMEOUT = 3
