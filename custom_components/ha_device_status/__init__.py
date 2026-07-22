"""Network Monitor integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

from .const import CONF_TYPE, CONF_WG_INTERFACE, CONF_WIREGUARD, DOMAIN
from .schema import CONFIG_SCHEMA  # noqa: F401 - required by Home Assistant's config validation
from .wireguard import async_setup_wireguard, async_teardown_wireguard

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Network Monitor component from YAML."""
    if DOMAIN not in config:
        return True

    domain_config = config[DOMAIN]
    hass.data.setdefault(DOMAIN, {})["yaml"] = domain_config

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
    """Set up a config entry: a WireGuard interface, or a monitored device."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    if entry.data.get(CONF_TYPE) == "wireguard":
        wg_up, wg_managed = await async_setup_wireguard(hass, entry.data)
        if not wg_up:
            _LOGGER.error(
                "Failed to bring up WireGuard interface %s for entry %s; "
                "ping checks over it will fail until it's brought up",
                entry.data.get(CONF_WG_INTERFACE),
                entry.title,
            )
            return False
        hass.data.setdefault(DOMAIN, {}).setdefault("wireguard_managed", {})[
            entry.entry_id
        ] = wg_managed
        return True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry: tear down a WireGuard interface, or a device."""
    if entry.data.get(CONF_TYPE) == "wireguard":
        managed = hass.data.get(DOMAIN, {}).get("wireguard_managed", {}).pop(
            entry.entry_id, False
        )
        if managed:
            await async_teardown_wireguard(entry.data[CONF_WG_INTERFACE])
        return True

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry when its options (or WireGuard details) change."""
    await hass.config_entries.async_reload(entry.entry_id)
