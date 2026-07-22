"""Network Monitor integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

from .const import CONF_WG_INTERFACE, CONF_WIREGUARD, DOMAIN
from .schema import CONFIG_SCHEMA  # noqa: F401 - required by Home Assistant's config validation
from .wireguard import async_setup_wireguard, async_teardown_wireguard

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Network Monitor component from YAML."""
    if DOMAIN not in config:
        return True

    domain_config = config[DOMAIN]
    hass.data[DOMAIN] = domain_config

    wg_config = domain_config.get(CONF_WIREGUARD)
    if wg_config:
        wg_up, wg_managed = await async_setup_wireguard(hass, wg_config)
        if not wg_up:
            _LOGGER.error(
                "Continuing without WireGuard interface %s; ping checks "
                "over it will fail until it's brought up",
                wg_config[CONF_WG_INTERFACE],
            )
        elif wg_managed:
            async def _teardown_wireguard(event):
                await async_teardown_wireguard(wg_config[CONF_WG_INTERFACE])

            hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, _teardown_wireguard
            )

    hass.async_create_task(
        discovery.async_load_platform(hass, Platform.BINARY_SENSOR, DOMAIN, {}, config)
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry (unused)."""
    return True
