"""Binary sensors for network monitoring."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import async_timeout
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.network import async_ping
from homeassistant.components.mqtt import async_subscribe
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_ITEMS,
    CONF_NOTIFY,
    CONF_NAME,
    CONF_TYPE,
    CONF_IP,
    CONF_PORT,
    CONF_TOPIC,
    CONF_PAYLOAD,
    DEFAULT_PAYLOAD,
)

_LOGGER = logging.getLogger(__name__)

ITEM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): vol.In(["ping", "port", "mqtt"]),
        vol.Optional(CONF_IP): cv.string,
        vol.Optional(CONF_PORT): cv.port,
        vol.Optional(CONF_TOPIC): cv.string,
        vol.Optional(CONF_PAYLOAD, default=DEFAULT_PAYLOAD): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ITEMS): vol.All(cv.ensure_list, [ITEM_SCHEMA]),
                vol.Optional(CONF_NOTIFY, default=[]): vol.All(cv.ensure_list, [cv.string]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SCAN_INTERVAL = timedelta(seconds=60)  # polling interval for ping/port


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the network monitor binary sensors."""
    if DOMAIN not in hass.data:
        return

    domain_config = hass.data[DOMAIN]
    items = domain_config.get(CONF_ITEMS, [])
    notify_names = domain_config.get(CONF_NOTIFY, [])

    sensors = []
    for item in items:
        name = item[CONF_NAME]
        item_type = item[CONF_TYPE]
        if item_type == "ping":
            sensors.append(PingSensor(hass, item, name in notify_names))
        elif item_type == "port":
            sensors.append(PortSensor(hass, item, name in notify_names))
        elif item_type == "mqtt":
            sensors.append(MqttSensor(hass, item, name in notify_names))

    async_add_entities(sensors, update_before_add=True)

    # Start periodic updates for ping and port sensors
    async def update_polling_sensors(now=None):
        for sensor in sensors:
            if isinstance(sensor, (PingSensor, PortSensor)):
                await sensor.async_update()

    async_track_time_interval(hass, update_polling_sensors, SCAN_INTERVAL)
    # Run once immediately
    await update_polling_sensors()


class NetworkMonitorSensor(BinarySensorEntity):
    """Base class for network monitor sensors."""

    def __init__(self, hass, item, notify_offline):
        self.hass = hass
        self._item = item
        self._name = item[CONF_NAME]
        self._notify_offline = notify_offline
        self._state = None
        self._was_online = None  # for triggering notifications
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_unique_id = f"network_monitor_{self._name}"

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {"type": self._item[CONF_TYPE]}

    async def async_update(self):
        """Polling update – to be overridden."""
        pass

    async def _set_state(self, new_state):
        """Set state and notify if offline transition."""
        old_state = self._state
        self._state = new_state
        self.async_write_ha_state()

        # Trigger notification on online -> offline transition
        if self._notify_offline and old_state is True and new_state is False:
            await self._notify_offline_event()

    async def _notify_offline_event(self):
        """Send a persistent notification."""
        self.hass.components.persistent_notification.async_create(
            f"Network monitor: {self._name} went offline!",
            title="Device Offline",
            notification_id=f"network_monitor_{self._name}_offline",
        )
        # You can also call a notify service, e.g.:
        # await self.hass.services.async_call("notify", "mobile_app", {"message": f"{self._name} is offline!"})


class PingSensor(NetworkMonitorSensor):
    """Ping an IP address."""

    def __init__(self, hass, item, notify_offline):
        super().__init__(hass, item, notify_offline)
        self._ip = item[CONF_IP]

    async def async_update(self):
        try:
            success = await async_ping(self.hass, self._ip, count=2, timeout=3)
            await self._set_state(success)
        except Exception as e:
            _LOGGER.error("Ping error for %s: %s", self._name, e)
            await self._set_state(False)


class PortSensor(NetworkMonitorSensor):
    """Check if a TCP port is open."""

    def __init__(self, hass, item, notify_offline):
        super().__init__(hass, item, notify_offline)
        self._ip = item[CONF_IP]
        self._port = item[CONF_PORT]

    async def async_update(self):
        try:
            async with async_timeout.timeout(5):
                reader, writer = await asyncio.open_connection(self._ip, self._port)
                writer.close()
                await writer.wait_closed()
                online = True
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            online = False
        except Exception as e:
            _LOGGER.error("Port check error for %s: %s", self._name, e)
            online = False
        await self._set_state(online)


class MqttSensor(NetworkMonitorSensor):
    """Subscribe to an MQTT topic and set state based on payload."""

    def __init__(self, hass, item, notify_offline):
        super().__init__(hass, item, notify_offline)
        self._topic = item[CONF_TOPIC]
        self._expected_payload = item.get(CONF_PAYLOAD, DEFAULT_PAYLOAD)
        self._unsubscribe = None

    async def async_added_to_hass(self):
        """Subscribe to MQTT topic when entity is added."""
        await super().async_added_to_hass()

        @callback
        def message_received(msg):
            """Handle incoming MQTT message."""
            payload = msg.payload
            is_online = payload == self._expected_payload
            self.hass.async_create_task(self._set_state(is_online))

        # Subscribe to MQTT topic
        self._unsubscribe = await async_subscribe(
            self.hass, self._topic, message_received, 0, "utf-8"
        )

    async def async_will_remove_from_hass(self):
        """Unsubscribe from MQTT topic."""
        if self._unsubscribe:
            self._unsubscribe()