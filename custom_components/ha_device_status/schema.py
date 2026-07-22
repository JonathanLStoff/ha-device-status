"""Voluptuous schemas for the ha_device_status YAML configuration.

Defined in one place and imported by __init__.py, since Home Assistant only
looks for CONFIG_SCHEMA on the component's __init__ module — a copy living in
binary_sensor.py is never actually applied.
"""
from __future__ import annotations

import os

from croniter import croniter
import voluptuous as vol

from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_COUNT,
    CONF_CRON,
    CONF_INTERFACE,
    CONF_IP,
    CONF_ITEMS,
    CONF_NAME,
    CONF_NOTIFY,
    CONF_NOTIFY_ONLINE,
    CONF_NOTIFY_SERVICES,
    CONF_PAYLOAD,
    CONF_PORT,
    CONF_TIMEOUT,
    CONF_TOPIC,
    CONF_TYPE,
    CONF_WG_ADDRESS,
    CONF_WG_CONFIG_PATH,
    CONF_WG_DNS,
    CONF_WG_INTERFACE,
    CONF_WG_LISTEN_PORT,
    CONF_WG_PEER_ALLOWED_IPS,
    CONF_WG_PEER_ENDPOINT,
    CONF_WG_PEER_PERSISTENT_KEEPALIVE,
    CONF_WG_PEER_PRESHARED_KEY,
    CONF_WG_PEER_PUBLIC_KEY,
    CONF_WG_PEERS,
    CONF_WG_PRIVATE_KEY,
    CONF_WIREGUARD,
    DEFAULT_COUNT,
    DEFAULT_CRON,
    DEFAULT_PAYLOAD,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

ITEM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): vol.In(["ping", "port", "mqtt"]),
        vol.Optional(CONF_IP): cv.string,
        vol.Optional(CONF_PORT): cv.port,
        vol.Optional(CONF_TOPIC): cv.string,
        vol.Optional(CONF_PAYLOAD, default=DEFAULT_PAYLOAD): cv.string,
        vol.Optional(CONF_INTERFACE): cv.string,
        vol.Optional(CONF_COUNT, default=DEFAULT_COUNT): cv.positive_int,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)


def _validate_cron(value: str) -> str:
    """Validate that a string is a parseable cron expression."""
    value = cv.string(value)
    if not croniter.is_valid(value):
        raise vol.Invalid(f"Invalid cron expression: {value}")
    return value


WIREGUARD_PEER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WG_PEER_PUBLIC_KEY): cv.string,
        vol.Optional(CONF_WG_PEER_PRESHARED_KEY): cv.string,
        vol.Optional(CONF_WG_PEER_ENDPOINT): cv.string,
        vol.Required(CONF_WG_PEER_ALLOWED_IPS): cv.string,
        vol.Optional(CONF_WG_PEER_PERSISTENT_KEEPALIVE): cv.positive_int,
    }
)


def _validate_wireguard(value: dict) -> dict:
    """Require either an existing conf file or enough to build one.

    If only config_path is given, the interface name is derived from its
    filename (matching what wg-quick itself does), so 'interface' doesn't
    need to be repeated.
    """
    config_path = value.get(CONF_WG_CONFIG_PATH)

    if not value.get(CONF_WG_INTERFACE):
        if not config_path:
            raise vol.Invalid(
                "wireguard config needs 'interface' set, or a 'config_path' "
                "to derive it from"
            )
        derived = os.path.splitext(os.path.basename(config_path))[0]
        if not derived:
            raise vol.Invalid(
                f"Cannot derive an interface name from config_path: {config_path}"
            )
        value[CONF_WG_INTERFACE] = derived

    if not config_path and (
        CONF_WG_PRIVATE_KEY not in value or CONF_WG_ADDRESS not in value
    ):
        raise vol.Invalid(
            "wireguard config needs either 'config_path', or 'private_key' "
            "and 'address' to build one"
        )
    return value


WIREGUARD_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(CONF_WG_INTERFACE): cv.string,
            vol.Optional(CONF_WG_CONFIG_PATH): cv.string,
            vol.Optional(CONF_WG_PRIVATE_KEY): cv.string,
            vol.Optional(CONF_WG_ADDRESS): cv.string,
            vol.Optional(CONF_WG_LISTEN_PORT): cv.port,
            vol.Optional(CONF_WG_DNS): cv.string,
            vol.Optional(CONF_WG_PEERS, default=[]): vol.All(
                cv.ensure_list, [WIREGUARD_PEER_SCHEMA]
            ),
        }
    ),
    _validate_wireguard,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ITEMS): vol.All(cv.ensure_list, [ITEM_SCHEMA]),
                vol.Optional(CONF_NOTIFY, default=[]): vol.All(
                    cv.ensure_list, [cv.string]
                ),
                vol.Optional(CONF_NOTIFY_SERVICES, default=[]): vol.All(
                    cv.ensure_list, [cv.string]
                ),
                vol.Optional(CONF_NOTIFY_ONLINE, default=False): cv.boolean,
                vol.Optional(CONF_CRON, default=DEFAULT_CRON): _validate_cron,
                vol.Optional(CONF_WIREGUARD): WIREGUARD_SCHEMA,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)
