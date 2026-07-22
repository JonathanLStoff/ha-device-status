"""Bring up a WireGuard interface so ping checks can reach devices over it.

Requires the `wireguard-tools` package (for `wg-quick`/`wg`) and NET_ADMIN on
the Home Assistant host/container. If the interface is already up (managed
outside of this integration), it is left alone and never torn down by us.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import stat
import tempfile

from homeassistant.core import HomeAssistant

from .const import (
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
)

_LOGGER = logging.getLogger(__name__)


async def _run(*cmd: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


async def _interface_exists(interface: str) -> bool:
    returncode, _, _ = await _run("ip", "link", "show", interface)
    return returncode == 0


def _render_conf(wg_config: dict) -> str:
    lines = ["[Interface]", f"PrivateKey = {wg_config[CONF_WG_PRIVATE_KEY]}"]
    lines.append(f"Address = {wg_config[CONF_WG_ADDRESS]}")
    if CONF_WG_LISTEN_PORT in wg_config:
        lines.append(f"ListenPort = {wg_config[CONF_WG_LISTEN_PORT]}")
    if CONF_WG_DNS in wg_config:
        lines.append(f"DNS = {wg_config[CONF_WG_DNS]}")

    for peer in wg_config.get(CONF_WG_PEERS, []):
        lines.append("")
        lines.append("[Peer]")
        lines.append(f"PublicKey = {peer[CONF_WG_PEER_PUBLIC_KEY]}")
        if CONF_WG_PEER_PRESHARED_KEY in peer:
            lines.append(f"PresharedKey = {peer[CONF_WG_PEER_PRESHARED_KEY]}")
        lines.append(f"AllowedIPs = {peer[CONF_WG_PEER_ALLOWED_IPS]}")
        if CONF_WG_PEER_ENDPOINT in peer:
            lines.append(f"Endpoint = {peer[CONF_WG_PEER_ENDPOINT]}")
        if CONF_WG_PEER_PERSISTENT_KEEPALIVE in peer:
            lines.append(
                f"PersistentKeepalive = {peer[CONF_WG_PEER_PERSISTENT_KEEPALIVE]}"
            )
    return "\n".join(lines) + "\n"


async def async_setup_wireguard(
    hass: HomeAssistant, wg_config: dict
) -> tuple[bool, bool]:
    """Bring up the configured WireGuard interface if it isn't already up.

    Returns (is_up, managed_by_us). managed_by_us is False when the
    interface already existed, so we know not to tear down something we
    didn't create.
    """
    interface = wg_config[CONF_WG_INTERFACE]

    if await _interface_exists(interface):
        _LOGGER.debug(
            "WireGuard interface %s already up, leaving it alone", interface
        )
        return True, False

    config_path = wg_config.get(CONF_WG_CONFIG_PATH)
    if config_path and not os.path.isabs(config_path):
        # Relative paths resolve against the Home Assistant config
        # directory (e.g. "wireguard/wg0.conf" -> "/config/wireguard/wg0.conf").
        config_path = hass.config.path(config_path)
    tmp_dir = None

    if not config_path:
        # wg-quick names the interface after the conf file's basename, so it
        # must be written as "<interface>.conf" for the name to line up.
        tmp_dir = tempfile.mkdtemp(prefix="ha_device_status_wg_")
        config_path = os.path.join(tmp_dir, f"{interface}.conf")
        with open(config_path, "w") as conf_file:
            conf_file.write(_render_conf(wg_config))
        os.chmod(config_path, stat.S_IRUSR | stat.S_IWUSR)

    returncode, stdout, stderr = await _run("wg-quick", "up", config_path)

    if tmp_dir:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if returncode != 0:
        _LOGGER.error(
            "Failed to bring up WireGuard interface %s: %s\n"
            "Make sure 'wireguard-tools' is installed and the Home "
            "Assistant host/container has NET_ADMIN capability.",
            interface,
            stderr or stdout,
        )
        return False, False

    _LOGGER.info("Brought up WireGuard interface %s", interface)
    return True, True


async def async_teardown_wireguard(interface: str) -> None:
    """Tear down a WireGuard interface this integration brought up."""
    returncode, _, stderr = await _run("wg-quick", "down", interface)
    if returncode != 0:
        _LOGGER.warning(
            "Failed to tear down WireGuard interface %s: %s", interface, stderr
        )
