"""Config flow for Device Status.

Each config entry represents either:
- a single monitored device (ping/port/mqtt), added through the UI
  (Settings -> Devices & Services -> Add Integration -> Device Status), or
- a WireGuard interface, which isn't monitored itself but can be picked as
  the "interface" for a ping device the same way a notify service is picked.

The options flow lets you change where notifications for a device go and how
often it's checked, or edit a WireGuard interface's connection details,
without having to remove and re-add the entry.
"""
from __future__ import annotations

import os
from typing import Any

from croniter import croniter
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import slugify

from .const import (
    CONF_COUNT,
    CONF_CRON,
    CONF_INTERFACE,
    CONF_IP,
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
    DEFAULT_COUNT,
    DEFAULT_CRON,
    DEFAULT_PAYLOAD,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

DEVICE_TYPES = ["ping", "port", "mqtt", "wireguard"]


def _notify_service_options(hass) -> list[str]:
    """List the notify.* services currently available (e.g. companion apps)."""
    return sorted(hass.services.async_services().get("notify", {}))


def _wireguard_interface_options(hass) -> list[str]:
    """List interface names from WireGuard entries already configured here."""
    return sorted(
        {
            entry.data[CONF_WG_INTERFACE]
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.data.get(CONF_TYPE) == "wireguard"
            and entry.data.get(CONF_WG_INTERFACE)
        }
    )


def _notify_schema(hass, defaults: dict) -> vol.Schema:
    """Schema for the notify-routing + schedule step, shared by both flows."""
    service_options = _notify_service_options(hass)
    return vol.Schema(
        {
            vol.Optional(
                CONF_NOTIFY_SERVICES,
                default=defaults.get(CONF_NOTIFY_SERVICES, []),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=service_options,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_NOTIFY, default=defaults.get(CONF_NOTIFY, True)
            ): bool,
            vol.Optional(
                CONF_NOTIFY_ONLINE, default=defaults.get(CONF_NOTIFY_ONLINE, False)
            ): bool,
            vol.Optional(
                CONF_CRON, default=defaults.get(CONF_CRON, DEFAULT_CRON)
            ): str,
        }
    )


def _wireguard_schema(defaults: dict) -> vol.Schema:
    """Schema for the WireGuard connection-details step/option, shared by both flows."""
    peer_defaults = (defaults.get(CONF_WG_PEERS) or [{}])[0]
    return vol.Schema(
        {
            vol.Optional(
                CONF_WG_CONFIG_PATH, default=defaults.get(CONF_WG_CONFIG_PATH, "")
            ): str,
            vol.Optional(
                CONF_WG_INTERFACE, default=defaults.get(CONF_WG_INTERFACE, "")
            ): str,
            vol.Optional(
                CONF_WG_ADDRESS, default=defaults.get(CONF_WG_ADDRESS, "")
            ): str,
            vol.Optional(
                CONF_WG_PRIVATE_KEY, default=defaults.get(CONF_WG_PRIVATE_KEY, "")
            ): str,
            vol.Optional(CONF_WG_LISTEN_PORT): int,
            vol.Optional(CONF_WG_DNS, default=defaults.get(CONF_WG_DNS, "")): str,
            vol.Optional(
                CONF_WG_PEER_PUBLIC_KEY,
                default=peer_defaults.get(CONF_WG_PEER_PUBLIC_KEY, ""),
            ): str,
            vol.Optional(
                CONF_WG_PEER_ENDPOINT,
                default=peer_defaults.get(CONF_WG_PEER_ENDPOINT, ""),
            ): str,
            vol.Optional(
                CONF_WG_PEER_ALLOWED_IPS,
                default=peer_defaults.get(CONF_WG_PEER_ALLOWED_IPS, ""),
            ): str,
            vol.Optional(CONF_WG_PEER_PERSISTENT_KEEPALIVE): int,
            vol.Optional(
                CONF_WG_PEER_PRESHARED_KEY,
                default=peer_defaults.get(CONF_WG_PEER_PRESHARED_KEY, ""),
            ): str,
        }
    )


def _finalize_wireguard(user_input: dict) -> tuple[dict | None, str | None]:
    """Turn the flat WireGuard form input into the shape wireguard.py expects.

    Returns (data, error_code). data is None when error_code is set.
    """
    config_path = user_input.get(CONF_WG_CONFIG_PATH) or None
    interface = user_input.get(CONF_WG_INTERFACE) or None

    if not interface:
        if not config_path:
            return None, "wireguard_needs_interface_or_config_path"
        derived = os.path.splitext(os.path.basename(config_path))[0]
        if not derived:
            return None, "wireguard_bad_config_path"
        interface = derived

    data: dict[str, Any] = {CONF_WG_INTERFACE: interface}

    if config_path:
        data[CONF_WG_CONFIG_PATH] = config_path
        return data, None

    private_key = user_input.get(CONF_WG_PRIVATE_KEY) or None
    address = user_input.get(CONF_WG_ADDRESS) or None
    peer_public_key = user_input.get(CONF_WG_PEER_PUBLIC_KEY) or None
    peer_allowed_ips = user_input.get(CONF_WG_PEER_ALLOWED_IPS) or None
    if not (private_key and address and peer_public_key and peer_allowed_ips):
        return None, "wireguard_needs_inline_fields"

    data[CONF_WG_PRIVATE_KEY] = private_key
    data[CONF_WG_ADDRESS] = address
    if user_input.get(CONF_WG_LISTEN_PORT):
        data[CONF_WG_LISTEN_PORT] = user_input[CONF_WG_LISTEN_PORT]
    if user_input.get(CONF_WG_DNS):
        data[CONF_WG_DNS] = user_input[CONF_WG_DNS]

    peer = {
        CONF_WG_PEER_PUBLIC_KEY: peer_public_key,
        CONF_WG_PEER_ALLOWED_IPS: peer_allowed_ips,
    }
    if user_input.get(CONF_WG_PEER_ENDPOINT):
        peer[CONF_WG_PEER_ENDPOINT] = user_input[CONF_WG_PEER_ENDPOINT]
    if user_input.get(CONF_WG_PEER_PERSISTENT_KEEPALIVE):
        peer[CONF_WG_PEER_PERSISTENT_KEEPALIVE] = user_input[
            CONF_WG_PEER_PERSISTENT_KEEPALIVE
        ]
    if user_input.get(CONF_WG_PEER_PRESHARED_KEY):
        peer[CONF_WG_PEER_PRESHARED_KEY] = user_input[CONF_WG_PEER_PRESHARED_KEY]

    data[CONF_WG_PEERS] = [peer]
    return data, None


class DeviceStatusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle adding one monitored device, or one WireGuard interface, via the UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(slugify(user_input[CONF_NAME]))
            self._abort_if_unique_id_configured()
            self._data.update(user_input)
            device_type = user_input[CONF_TYPE]
            if device_type == "ping":
                return await self.async_step_ping()
            if device_type == "port":
                return await self.async_step_port()
            if device_type == "wireguard":
                return await self.async_step_wireguard()
            return await self.async_step_mqtt()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_TYPE, default="ping"): SelectSelector(
                    SelectSelectorConfig(
                        options=DEVICE_TYPES, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_ping(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notify()

        interface_options = _wireguard_interface_options(self.hass)
        schema = vol.Schema(
            {
                vol.Required(CONF_IP): str,
                vol.Optional(CONF_INTERFACE): SelectSelector(
                    SelectSelectorConfig(
                        options=interface_options,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_COUNT, default=DEFAULT_COUNT): int,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
            }
        )
        return self.async_show_form(step_id="ping", data_schema=schema)

    async def async_step_port(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notify()

        schema = vol.Schema(
            {
                vol.Required(CONF_IP): str,
                vol.Required(CONF_PORT): int,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
            }
        )
        return self.async_show_form(step_id="port", data_schema=schema)

    async def async_step_mqtt(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notify()

        schema = vol.Schema(
            {
                vol.Required(CONF_TOPIC): str,
                vol.Optional(CONF_PAYLOAD, default=DEFAULT_PAYLOAD): str,
            }
        )
        return self.async_show_form(step_id="mqtt", data_schema=schema)

    async def async_step_wireguard(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            data, error = _finalize_wireguard(user_input)
            if error:
                errors["base"] = error
            else:
                self._data.update(data)
                return self.async_create_entry(
                    title=self._data[CONF_NAME], data=self._data
                )

        return self.async_show_form(
            step_id="wireguard",
            data_schema=_wireguard_schema({}),
            errors=errors,
        )

    async def async_step_notify(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            cron = user_input.get(CONF_CRON, DEFAULT_CRON)
            if not croniter.is_valid(cron):
                errors[CONF_CRON] = "invalid_cron"
            else:
                options = {
                    CONF_NOTIFY_SERVICES: user_input.get(CONF_NOTIFY_SERVICES, []),
                    CONF_NOTIFY: user_input.get(CONF_NOTIFY, True),
                    CONF_NOTIFY_ONLINE: user_input.get(CONF_NOTIFY_ONLINE, False),
                    CONF_CRON: cron,
                }
                return self.async_create_entry(
                    title=self._data[CONF_NAME], data=self._data, options=options
                )

        return self.async_show_form(
            step_id="notify",
            data_schema=_notify_schema(self.hass, {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        if config_entry.data.get(CONF_TYPE) == "wireguard":
            return WireguardOptionsFlow()
        return DeviceStatusOptionsFlow()


class DeviceStatusOptionsFlow(config_entries.OptionsFlow):
    """Edit notify routing and check schedule for an existing device."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.options

        if user_input is not None:
            cron = user_input.get(CONF_CRON, DEFAULT_CRON)
            if not croniter.is_valid(cron):
                errors[CONF_CRON] = "invalid_cron"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_notify_schema(self.hass, current),
            errors=errors,
        )


class WireguardOptionsFlow(config_entries.OptionsFlow):
    """Edit an existing WireGuard interface's connection details."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        # async_step_init is the mandatory entry point for an options flow,
        # but the form below is shown with step_id="wireguard" - resubmitting
        # it gets routed to async_step_wireguard, not back to this method.
        return await self.async_step_wireguard(user_input)

    async def async_step_wireguard(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.data

        if user_input is not None:
            data, error = _finalize_wireguard(user_input)
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data={**self.config_entry.data, **data}
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="wireguard",
            data_schema=_wireguard_schema(current),
            errors=errors,
        )
