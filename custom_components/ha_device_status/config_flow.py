"""Config flow for Device Status.

Each config entry represents a single monitored device, added through the
UI (Settings -> Devices & Services -> Add Integration -> Device Status).
The options flow lets you change where notifications for that device go and
how often it's checked, without having to remove and re-add it.
"""
from __future__ import annotations

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
    DEFAULT_COUNT,
    DEFAULT_CRON,
    DEFAULT_PAYLOAD,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

DEVICE_TYPES = ["ping", "port", "mqtt"]


def _notify_service_options(hass) -> list[str]:
    """List the notify.* services currently available (e.g. companion apps)."""
    return sorted(hass.services.async_services().get("notify", {}))


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


class DeviceStatusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle adding one monitored device via the UI."""

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

        schema = vol.Schema(
            {
                vol.Required(CONF_IP): str,
                vol.Optional(CONF_INTERFACE): str,
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
    ) -> "DeviceStatusOptionsFlow":
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
