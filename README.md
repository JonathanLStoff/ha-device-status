# ha-device-status
Home Assistant integration that monitors devices by checking ping reachability, TCP ports, or MQTT topics and exposing the result as binary sensors.

[![GitHub Release](https://img.shields.io/github/release/JonathanLStoff/ha-device-status.svg?style=flat-square)](https://github.com/JonathanLStoff/ha-device-status/releases)
[![License](https://img.shields.io/github/license/JonathanLStoff/ha-device-status.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-default-orange.svg?style=flat-square)](https://hacs.xyz)

## What it does

This integration creates binary sensor entities for devices you want to monitor. Each item can be configured as one of the following:

- Ping an IP address (optionally over a specific interface, such as a WireGuard tunnel)
- Check whether a TCP port is open
- Subscribe to an MQTT topic and compare the payload to an expected value

When a monitored item goes offline it can:

- Create a persistent notification in Home Assistant
- Push a notification to your phone(s) via the Home Assistant companion app
- Optionally push a follow-up when the device recovers

How often ping/port devices are checked is controlled by a **cron expression**.

## Installation

### HACS

The easiest way to install this integration is through [HACS](https://hacs.xyz/):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JonathanLStoff&repository=ha-device-status&category=integration)

Then open HACS, go to Integrations, and search for "ha-device-status".

### Manual installation

Copy the folder [custom_components/ha_device_status](custom_components/ha_device_status) into your Home Assistant configuration's custom_components directory.

## Configuration

Add a configuration block like the one in [example.configuration.yaml](example.configuration.yaml) to your Home Assistant configuration.

Example:

```yaml
ha_device_status:
  cron: "*/5 * * * *"            # how often to check ping/port devices
  notify_services:               # companion-app services, one per phone
    - mobile_app_johns_iphone
  notify_online: true            # also notify when a device recovers
  items:
    - name: "Router"
      type: ping
      ip: 192.168.1.1

    - name: "Remote NAS"         # only reachable over WireGuard
      type: ping
      ip: 10.0.0.5
      interface: wg0             # send the ping out the WireGuard interface

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
    - "Remote NAS"
    - "Web Server"
```

### Options

| Key | Scope | Description |
| --- | --- | --- |
| `cron` | top level | Cron expression for how often ping/port devices are checked. Default `*/1 * * * *` (every minute). |
| `notify_services` | top level | List of Home Assistant companion-app notify services (e.g. `mobile_app_johns_iphone`). Find yours under **Developer Tools → Actions**. |
| `notify_online` | top level | If `true`, also push a notification when a device comes back online. Default `false`. |
| `notify_offline` | top level | List of item names that should trigger notifications when offline. |
| `interface` | per ping item | Network interface to bind the ping to, e.g. `wg0` to ping a device across a WireGuard tunnel. |
| `count` | per ping/port item | Number of attempts. Default `2`. |
| `timeout` | per ping/port item | Per-attempt timeout in seconds. Default `3`. |

**Notifying phones:** each phone with the Home Assistant companion app exposes a `notify.mobile_app_<device>` service. List those service names (without the `notify.` prefix) under `notify_services`, and list which devices should trigger alerts under `notify_offline`.

**WireGuard pings:** pinging a device by its VPN IP works automatically if your Home Assistant host routes that subnet over WireGuard. Set `interface: wg0` (or your tunnel's interface name) to force the ping out that specific interface.

If you use MQTT-based checks, make sure the MQTT integration is configured in Home Assistant.

## Lovelace example

A sample Lovelace card configuration is available in [example.lovelace](example.lovelace).

## Maintainers

- Jonathan Stoff
