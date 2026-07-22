"""Binary sensors for network monitoring."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import async_timeout
from croniter import croniter
from homeassistant.components import persistent_notification
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.mqtt import async_subscribe
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.dt as dt_util

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
    DEFAULT_COUNT,
    DEFAULT_CRON,
    DEFAULT_PAYLOAD,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _device_info(entry: ConfigEntry, item: dict) -> DeviceInfo:
    """One Home Assistant device per monitored device.

    Sharing a single device across many config entries is unreliable in
    Home Assistant's device registry (entities can fail to attach to it
    correctly), so each entry gets its own device instead — the standard,
    robust pattern. It still shows up under Settings -> Devices & Services,
    and its "Add to dashboard" button works as expected.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=item[CONF_NAME],
        manufacturer="ha-device-status",
        model=item[CONF_TYPE].capitalize(),
    )


async def _async_ping(
    ip: str, count: int, timeout: int, interface: str | None = None
) -> bool:
    """Ping a host with the system ping binary, optionally via an interface.

    Binding to an interface (e.g. ``wg0``) forces the ICMP packets out a
    specific route such as a WireGuard tunnel.
    """
    cmd = ["ping", "-n", "-q", "-c", str(count), "-W", str(timeout)]
    if interface:
        cmd += ["-I", interface]
    cmd.append(ip)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as err:
        _LOGGER.error("Failed to run ping for %s: %s", ip, err)
        return False

    try:
        # Give ping enough time for all attempts plus a small buffer.
        async with async_timeout.timeout(count * timeout + 5):
            await proc.communicate()
    except asyncio.TimeoutError:
        proc.kill()
        return False

    return proc.returncode == 0


def _start_cron_polling(hass: HomeAssistant, cron_expr: str, sensors: list):
    """Poll `sensors` on a cron schedule. Returns a callable that cancels it.

    The very first update is left to `update_before_add=True` on
    `async_add_entities`, which Home Assistant already runs in proper
    sequence with attaching the entity. Firing an extra update here too
    raced against that attachment (entity had no `hass`/`entity_id` yet),
    producing "Attribute hass is None" / "No entity id specified" errors.
    """
    state = {"cancelled": False, "unsub": None}

    async def update_sensors(now=None):
        await asyncio.gather(*(sensor.async_update() for sensor in sensors))

    def schedule_next():
        if state["cancelled"]:
            return
        next_time = croniter(cron_expr, dt_util.now()).get_next(datetime)
        state["unsub"] = async_track_point_in_time(hass, run_and_reschedule, next_time)

    async def run_and_reschedule(now):
        await update_sensors()
        schedule_next()

    @callback
    def cancel():
        state["cancelled"] = True
        if state["unsub"]:
            state["unsub"]()

    schedule_next()
    return cancel


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up network monitor binary sensors configured via YAML."""
    domain_config = hass.data.get(DOMAIN, {}).get("yaml")
    if not domain_config:
        return

    items = domain_config.get(CONF_ITEMS, [])
    notify_names = domain_config.get(CONF_NOTIFY, [])
    notify_services = domain_config.get(CONF_NOTIFY_SERVICES, [])
    notify_online = domain_config.get(CONF_NOTIFY_ONLINE, False)
    cron_expr = domain_config.get(CONF_CRON, DEFAULT_CRON)

    sensors: list[NetworkMonitorSensor] = []
    for item in items:
        name = item[CONF_NAME]
        item_type = item[CONF_TYPE]
        notify_offline = name in notify_names
        if item_type == "ping":
            sensors.append(
                PingSensor(hass, item, notify_offline, notify_services, notify_online)
            )
        elif item_type == "port":
            sensors.append(
                PortSensor(hass, item, notify_offline, notify_services, notify_online)
            )
        elif item_type == "mqtt":
            sensors.append(
                MqttSensor(hass, item, notify_offline, notify_services, notify_online)
            )

    async_add_entities(sensors, update_before_add=True)

    polling_sensors = [s for s in sensors if isinstance(s, (PingSensor, PortSensor))]
    if polling_sensors:
        _start_cron_polling(hass, cron_expr, polling_sensors)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor for a single device added via the UI."""
    item = dict(entry.data)
    options = entry.options
    notify_offline = options.get(CONF_NOTIFY, True)
    notify_services = options.get(CONF_NOTIFY_SERVICES, [])
    notify_online = options.get(CONF_NOTIFY_ONLINE, False)
    cron_expr = options.get(CONF_CRON, DEFAULT_CRON)

    unique_id = f"network_monitor_entry_{entry.entry_id}"
    device_info = _device_info(entry, item)
    item_type = item[CONF_TYPE]
    if item_type == "ping":
        sensor = PingSensor(
            hass,
            item,
            notify_offline,
            notify_services,
            notify_online,
            unique_id,
            device_info,
        )
    elif item_type == "port":
        sensor = PortSensor(
            hass,
            item,
            notify_offline,
            notify_services,
            notify_online,
            unique_id,
            device_info,
        )
    else:
        sensor = MqttSensor(
            hass,
            item,
            notify_offline,
            notify_services,
            notify_online,
            unique_id,
            device_info,
        )

    async_add_entities([sensor], update_before_add=True)

    if isinstance(sensor, (PingSensor, PortSensor)):
        cancel = _start_cron_polling(hass, cron_expr, [sensor])
        entry.async_on_unload(cancel)


class NetworkMonitorSensor(BinarySensorEntity):
    """Base class for network monitor sensors."""

    def __init__(
        self,
        hass,
        item,
        notify_offline,
        notify_services,
        notify_online,
        unique_id=None,
        device_info=None,
    ):
        self.hass = hass
        self._item = item
        self._name = item[CONF_NAME]
        self._notify_offline = notify_offline
        self._notify_services = notify_services
        self._notify_online = notify_online
        self._state = None
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_unique_id = unique_id or f"network_monitor_{self._name}"
        self._attr_device_info = device_info
        # We drive updates ourselves via the cron schedule / MQTT subscription;
        # without this, HA's generic entity polling would also call
        # async_update() on its own default interval, doubling checks.
        self._attr_should_poll = False

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._state

    @property
    def extra_state_attributes(self):
        attrs = {"type": self._item[CONF_TYPE]}
        if CONF_INTERFACE in self._item:
            attrs["interface"] = self._item[CONF_INTERFACE]
        return attrs

    async def async_update(self):
        """Polling update – to be overridden."""

    async def _set_state(self, new_state):
        """Set state and notify on transitions."""
        old_state = self._state
        self._state = new_state
        self.async_write_ha_state()

        if old_state is None or old_state == new_state:
            return

        # online -> offline
        if old_state is True and new_state is False:
            await self._notify(
                f"{self._name} went offline!",
                title="Device Offline",
                notification_id=f"network_monitor_{self._name}_offline",
                send=self._notify_offline,
            )
        # offline -> online
        elif old_state is False and new_state is True:
            await self._notify(
                f"{self._name} is back online.",
                title="Device Online",
                notification_id=f"network_monitor_{self._name}_offline",
                send=self._notify_offline and self._notify_online,
                dismiss=True,
            )

    async def _notify(self, message, title, notification_id, send, dismiss=False):
        """Send/clear a persistent notification and push to phones."""
        if dismiss:
            persistent_notification.async_dismiss(self.hass, notification_id)
        else:
            persistent_notification.async_create(
                self.hass, message, title=title, notification_id=notification_id
            )

        if not send:
            return

        # Push to the Home Assistant companion app on each configured phone.
        for service in self._notify_services:
            try:
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {"title": title, "message": message},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001 - never let a bad service break polling
                _LOGGER.error("Failed to notify via notify.%s: %s", service, err)


class PingSensor(NetworkMonitorSensor):
    """Ping an IP address, optionally over a specific interface (e.g. WireGuard)."""

    def __init__(
        self,
        hass,
        item,
        notify_offline,
        notify_services,
        notify_online,
        unique_id=None,
        device_info=None,
    ):
        super().__init__(
            hass,
            item,
            notify_offline,
            notify_services,
            notify_online,
            unique_id,
            device_info,
        )
        self._ip = item[CONF_IP]
        self._interface = item.get(CONF_INTERFACE)
        self._count = item.get(CONF_COUNT, DEFAULT_COUNT)
        self._timeout = item.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

    async def async_update(self):
        try:
            success = await _async_ping(
                self._ip, self._count, self._timeout, self._interface
            )
            await self._set_state(success)
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Ping error for %s: %s", self._name, e)
            await self._set_state(False)


class PortSensor(NetworkMonitorSensor):
    """Check if a TCP port is open."""

    def __init__(
        self,
        hass,
        item,
        notify_offline,
        notify_services,
        notify_online,
        unique_id=None,
        device_info=None,
    ):
        super().__init__(
            hass,
            item,
            notify_offline,
            notify_services,
            notify_online,
            unique_id,
            device_info,
        )
        self._ip = item[CONF_IP]
        self._port = item[CONF_PORT]
        self._timeout = item.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

    async def async_update(self):
        try:
            async with async_timeout.timeout(self._timeout):
                reader, writer = await asyncio.open_connection(self._ip, self._port)
                writer.close()
                await writer.wait_closed()
                online = True
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            online = False
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Port check error for %s: %s", self._name, e)
            online = False
        await self._set_state(online)


class MqttSensor(NetworkMonitorSensor):
    """Subscribe to an MQTT topic and set state based on payload."""

    def __init__(
        self,
        hass,
        item,
        notify_offline,
        notify_services,
        notify_online,
        unique_id=None,
        device_info=None,
    ):
        super().__init__(
            hass,
            item,
            notify_offline,
            notify_services,
            notify_online,
            unique_id,
            device_info,
        )
        self._topic = item[CONF_TOPIC]
        self._expected_payload = item.get(CONF_PAYLOAD, DEFAULT_PAYLOAD)
        self._unsubscribe = None

    async def async_added_to_hass(self):
        """Subscribe to MQTT topic when entity is added."""
        await super().async_added_to_hass()

        @callback
        def message_received(msg):
            """Handle incoming MQTT message."""
            is_online = msg.payload == self._expected_payload
            self.hass.async_create_task(self._set_state(is_online))

        self._unsubscribe = await async_subscribe(
            self.hass, self._topic, message_received, 0, "utf-8"
        )

    async def async_will_remove_from_hass(self):
        """Unsubscribe from MQTT topic."""
        if self._unsubscribe:
            self._unsubscribe()
