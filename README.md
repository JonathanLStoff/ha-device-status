# ha-device-status
Home Assistant integration that monitors devices by checking ping reachability, TCP ports, or MQTT topics and exposing the result as binary sensors.

[![GitHub Release](https://img.shields.io/github/release/JonathanLStoff/ha-device-status.svg?style=flat-square)](https://github.com/JonathanLStoff/ha-device-status/releases)
[![License](https://img.shields.io/github/license/JonathanLStoff/ha-device-status.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-default-orange.svg?style=flat-square)](https://hacs.xyz)

## What it does

This integration creates binary sensor entities for devices you want to monitor. Each item can be configured as one of the following:

- Ping an IP address
- Check whether a TCP port is open
- Subscribe to an MQTT topic and compare the payload to an expected value

It also supports optional persistent notifications when a monitored item goes offline.

## Installation

### HACS

The easiest way to install this integration is through [HACS](https://hacs.xyz/):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JonathanLStoff&repository=ha-device-status&category=integration)

Then open HACS, go to Integrations, and search for "ha-device-status".

### Manual installation

Copy the folder [custom_components/ha-device-status](custom_components/ha-device-status) into your Home Assistant configuration's custom_components directory.

## Configuration

Add a configuration block like the one in [example.configuration.yaml](example.configuration.yaml) to your Home Assistant configuration.

Example:

```yaml
ha_device_status:
  items:
    - name: "Router"
      type: ping
      ip: 192.168.1.1

    - name: "Web Server"
      type: port
      ip: 192.168.1.10
      port: 80

    - name: "MQTT Device"
      type: mqtt
      topic: "home/device/status"
      payload: "online"

  notify_offline:
    - "Router"
    - "Web Server"
```

If you use MQTT-based checks, make sure the MQTT integration is configured in Home Assistant.

## Lovelace example

A sample Lovelace card configuration is available in [example.lovelace](example.lovelace).

## Maintainers

- Jonathan Stoff
