"""Establish in-process WireGuard tunnels for TCP reachability checks.

Uses the `wireguard-requests` package (Cloudflare's boringtun + smoltcp,
via Rust/PyO3 bindings) to speak the WireGuard protocol entirely in
userspace: no system network interface, no `wireguard-tools`/`wg-quick`
binary, no NET_ADMIN capability, nothing to install at the OS level.

Only TCP is supported (this library has no ICMP), so a "ping" device
routed through one of these tunnels performs a TCP-connect reachability
check instead of a real ICMP echo - see binary_sensor.py.

We deliberately never use wireguard_requests.wireguard_context(): it
monkeypatches socket.socket and ssl.SSLContext.wrap_socket process-wide for
its entire duration, which would silently reroute *any* unrelated Home
Assistant network activity happening concurrently in this same process.
Instead we build the tunnel directly and drive it with AsyncWireGuardSocket,
which has no such global side effects.
"""
from __future__ import annotations

import asyncio
import logging
import os

from homeassistant.core import HomeAssistant

from .const import (
    CONF_WG_ADDRESS,
    CONF_WG_CONFIG_PATH,
    CONF_WG_DNS,
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


def _build_native_tunnel(wg_config: dict, config_path: str | None):
    """Build the native (Rust-backed) tunnel. Runs in an executor thread.

    Does file I/O (for config_path) and tunnel construction, neither of
    which should run on the event loop.
    """
    from wireguard_requests import Peer, WireGuardConfig, _native

    if config_path:
        config = WireGuardConfig.from_file(config_path)
    else:
        address = wg_config[CONF_WG_ADDRESS]
        prefix_len = 24
        if "/" in address:
            address, prefix_str = address.split("/", 1)
            prefix_len = int(prefix_str)

        peers = [
            Peer(
                public_key=peer[CONF_WG_PEER_PUBLIC_KEY],
                endpoint=peer[CONF_WG_PEER_ENDPOINT],
                allowed_ips=[
                    ip.strip() for ip in peer[CONF_WG_PEER_ALLOWED_IPS].split(",")
                ],
                persistent_keepalive=peer.get(CONF_WG_PEER_PERSISTENT_KEEPALIVE),
                preshared_key=peer.get(CONF_WG_PEER_PRESHARED_KEY),
            )
            for peer in wg_config.get(CONF_WG_PEERS, [])
        ]
        dns = wg_config.get(CONF_WG_DNS)
        config = WireGuardConfig(
            private_key=wg_config[CONF_WG_PRIVATE_KEY],
            address=address,
            prefix_len=prefix_len,
            peers=peers,
            listen_port=wg_config.get(CONF_WG_LISTEN_PORT, 0),
            dns=[dns] if dns else [],
        )

    return _native.WgTunnel(config.to_native())


class WireGuardTunnel:
    """A single in-process WireGuard tunnel, used for TCP reachability checks."""

    def __init__(self, native_tunnel) -> None:
        self._tunnel = native_tunnel

    async def check_tcp(self, host: str, port: int, timeout: float) -> bool:
        """Return True if a TCP connection through the tunnel succeeds."""
        from wireguard_requests import AsyncWireGuardSocket
        from wireguard_requests.exceptions import WireGuardError

        sock = AsyncWireGuardSocket(self._tunnel)
        try:
            await asyncio.wait_for(sock.connect((host, port)), timeout=timeout)
            return True
        except (WireGuardError, OSError, asyncio.TimeoutError):
            return False
        finally:
            await sock.close()

    def close(self) -> None:
        """Tear down the tunnel."""
        self._tunnel.close()


async def async_create_wireguard_tunnel(
    hass: HomeAssistant, wg_config: dict
) -> WireGuardTunnel | None:
    """Build and start a WireGuard tunnel from the given config.

    Returns None (and logs an error) if the 'wireguard-requests' package
    isn't installed, or the config is invalid, or the tunnel fails to
    initialize (e.g. bad keys, malformed config file).
    """
    config_path = wg_config.get(CONF_WG_CONFIG_PATH)
    if config_path and not os.path.isabs(config_path):
        # Relative paths resolve against the Home Assistant config
        # directory (e.g. "wireguard/wg0.conf" -> "/config/wireguard/wg0.conf").
        config_path = hass.config.path(config_path)

    try:
        native_tunnel = await hass.async_add_executor_job(
            _build_native_tunnel, wg_config, config_path
        )
    except ImportError:
        _LOGGER.error(
            "The 'wireguard-requests' package is not installed; this "
            "WireGuard tunnel can't be set up. Reinstall this integration "
            "through HACS so its requirements are installed."
        )
        return None
    except Exception as err:  # noqa: BLE001 - surfaces config/library errors as a clean log line
        _LOGGER.error("Failed to set up WireGuard tunnel: %s", err)
        return None

    return WireGuardTunnel(native_tunnel)
