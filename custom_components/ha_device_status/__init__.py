"""Network Monitor integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

from .const import CONF_NAME, CONF_TYPE, CONF_WG_INTERFACE, CONF_WIREGUARD, DOMAIN
from .schema import CONFIG_SCHEMA  # noqa: F401 - required by Home Assistant's config validation
from .wireguard import async_create_wireguard_tunnel

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]


def _wireguard_tunnels(hass: HomeAssistant) -> dict:
    return hass.data.setdefault(DOMAIN, {}).setdefault("wireguard_tunnels", {})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Network Monitor component from YAML."""
    if DOMAIN not in config:
        return True

    domain_config = config[DOMAIN]
    hass.data.setdefault(DOMAIN, {})["yaml"] = domain_config

    wg_config = domain_config.get(CONF_WIREGUARD)
    if wg_config:
        tunnel = await async_create_wireguard_tunnel(hass, wg_config)
        if tunnel is None:
            _LOGGER.error(
                "Continuing without WireGuard tunnel %s; ping/port checks "
                "routed through it will fail",
                wg_config.get(CONF_WG_INTERFACE, "(unnamed)"),
            )
        else:
            name = wg_config.get(CONF_WG_INTERFACE, "yaml")
            _wireguard_tunnels(hass)[name] = tunnel

    hass.async_create_task(
        discovery.async_load_platform(hass, Platform.BINARY_SENSOR, DOMAIN, {}, config)
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry: a WireGuard tunnel, or a monitored device."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    if entry.data.get(CONF_TYPE) == "wireguard":
        tunnel = await async_create_wireguard_tunnel(hass, entry.data)
        if tunnel is None:
            _LOGGER.error(
                "Failed to set up WireGuard tunnel %s; ping/port checks "
                "routed through it will fail",
                entry.title,
            )
            return False
        _wireguard_tunnels(hass)[entry.data[CONF_NAME]] = tunnel
        return True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry: tear down a WireGuard tunnel, or a device."""
    if entry.data.get(CONF_TYPE) == "wireguard":
        tunnel = _wireguard_tunnels(hass).pop(entry.data[CONF_NAME], None)
        if tunnel is not None:
            tunnel.close()
        return True

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry when its options (or WireGuard details) change."""
    await hass.config_entries.async_reload(entry.entry_id)
