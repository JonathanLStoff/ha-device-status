# ha-device-status
Home Assistant integration that monitors devices by checking ping reachability, TCP ports, or MQTT topics and exposing the result as binary sensors.

[![GitHub Release](https://img.shields.io/github/release/JonathanLStoff/ha-device-status.svg?style=flat-square)](https://github.com/JonathanLStoff/ha-device-status/releases)
[![License](https://img.shields.io/github/license/JonathanLStoff/ha-device-status.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-default-orange.svg?style=flat-square)](https://hacs.xyz)

## What it does

This integration creates one binary sensor per device you want to monitor. Each device can be checked one of these ways:

- Ping an IP address (optionally over a specific interface, such as a WireGuard tunnel)
- Check whether a TCP port is open
- Subscribe to an MQTT topic and compare the payload to an expected value

It can also bring up a WireGuard interface itself, so you don't have to configure the tunnel outside of Home Assistant first.

When a monitored device goes offline it can:

- Create a persistent notification in Home Assistant
- Push a notification to specific `notify.*` services (e.g. your phone's companion app) — chosen per device
- Optionally push a follow-up when the device recovers

How often each device is checked is controlled by a **cron expression**, set per device.

## Installation

### HACS

The easiest way to install this integration is through [HACS](https://hacs.xyz/):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JonathanLStoff&repository=ha-device-status&category=integration)

Then open HACS, go to Integrations, and search for "ha-device-status".

### Manual installation

Copy the folder [custom_components/ha_device_status](custom_components/ha_device_status) into your Home Assistant configuration's custom_components directory.

## Configuration via the UI (recommended)

After installing, go to **Settings → Devices & Services → Add Integration**, search for "Device Status", and add it. Each time you run through the flow you add **one device**:

1. **Name & type** — pick `ping`, `port`, `mqtt`, or `wireguard`.
2. **Connection details**:
   - `ping` — IP/hostname, attempt count, timeout, and an **interface** you pick from a dropdown (any WireGuard tunnel you've already added through this integration shows up as an option, the same way notify services do below — or type your own interface name if it's managed elsewhere).
   - `port` — IP/hostname and port.
   - `mqtt` — topic and expected payload.
   - `wireguard` — see "Adding a WireGuard tunnel" below. This isn't a monitored device (no binary sensor); it exists so its interface can be selected by `ping` devices.
3. **Notifications & schedule** *(skipped for `wireguard`)* — pick which `notify.*` services (e.g. your phone's Home Assistant companion app) should be alerted for *this device*, whether to also notify on recovery, and the cron schedule for how often it's checked.

Repeat "Add Integration" for each additional device — every device is its own entry with its own notification routing and schedule. To change a device's notify services/schedule, or a WireGuard tunnel's connection details, click **Configure** on that entry in Devices & Services.

To route notifications to a phone, install the [Home Assistant companion app](https://www.home-assistant.io/companion-app/) on it first — its `notify.mobile_app_<device>` service will then show up as an option in the flow.

### Adding a WireGuard tunnel

Add a device with type `wireguard` to have the integration bring up the tunnel itself, either:

- **From an existing config**: set "Existing wg-quick config file path" to a `wg-quick`-style `.conf` file. The interface name is derived from the filename (e.g. `wg0.conf` → `wg0`) unless you set one explicitly.
- **Inline**: leave the config path blank and fill in interface, address, private key, and the peer's public key + allowed IPs (endpoint, keepalive, and preshared key are optional). This models a single-peer client setup — the common case of connecting out to one VPN server.

This requires `wireguard-tools` (`wg`, `wg-quick`) and `NET_ADMIN` capability on the Home Assistant host/container. If the interface already exists (managed some other way), the integration leaves it alone and won't tear it down; if it brought the interface up itself, it tears it down when that entry is removed or Home Assistant stops.

Once added, pick that tunnel's interface from the dropdown when adding a `ping` device.

## Configuration via YAML (advanced / bulk setup)

YAML configuration still works and is useful for defining many devices at once, or for the global `wireguard` interface setup below (which isn't tied to any single device). Add a block like the one in [example.configuration.yaml](example.configuration.yaml) to your Home Assistant configuration.

Example:

```yaml
ha_device_status:
  wireguard:                     # optional: bring up a tunnel yourself
    interface: wg0
    address: 10.10.0.2/24
    private_key: !secret wg_private_key
    peers:
      - public_key: "SERVER_PUBLIC_KEY"
        endpoint: "vpn.example.com:51820"
        allowed_ips: "10.10.0.0/24"

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

### YAML options

| Key | Scope | Description |
| --- | --- | --- |
| `wireguard` | top level | Optional. Have the integration bring up a WireGuard interface itself. See below. |
| `cron` | top level | Cron expression for how often ping/port devices are checked. Default `*/1 * * * *` (every minute). |
| `notify_services` | top level | List of Home Assistant companion-app notify services (e.g. `mobile_app_johns_iphone`). Find yours under **Developer Tools → Actions**. |
| `notify_online` | top level | If `true`, also push a notification when a device comes back online. Default `false`. |
| `notify_offline` | top level | List of item names that should trigger notifications when offline. |
| `interface` | per ping item | Network interface to bind the ping to, e.g. `wg0` to ping a device across a WireGuard tunnel. |
| `count` | per ping/port item | Number of attempts. Default `2`. |
| `timeout` | per ping/port item | Per-attempt timeout in seconds. Default `3`. |

**Notifying phones:** each phone with the Home Assistant companion app exposes a `notify.mobile_app_<device>` service. List those service names (without the `notify.` prefix) under `notify_services`, and list which devices should trigger alerts under `notify_offline`.

**WireGuard tunnel:** the `wireguard` block will bring the interface up for you at startup, either from inline keys/peers or from an existing wg-quick config file (`config_path`). When using `config_path`, `interface` can be omitted — it's derived from the filename the same way `wg-quick` does (e.g. `wg0.conf` → interface `wg0`); set `interface` explicitly if you want to override that. This requires:

- `wireguard-tools` (`wg`, `wg-quick`) installed on the Home Assistant host/container
- `NET_ADMIN` capability available to that host/container

If the interface already exists (e.g. you set it up another way), the integration leaves it alone and won't tear it down on shutdown. If it brought the interface up itself, it tears it down when Home Assistant stops. Once the tunnel is up, set `interface: wg0` (matching the `wireguard.interface` name) on any ping item that needs to reach a device across it.

If you use MQTT-based checks, make sure the MQTT integration is configured in Home Assistant.

## Dashboard status card

Every monitored device (ping/port/mqtt) you add through the UI is grouped under one shared **"Device Status"** device, so you can add a status card entirely through the UI, no YAML at all:

1. Go to **Settings → Devices & Services → Device Status**, then open the **Devices** tab and click into the **Device Status** device (it lists every ping/port/mqtt device you've added).
2. Click **Add to dashboard** (top of the device page).
3. Pick the entities you want (or select all), choose a dashboard/view, and pick a card type (an Entities or Glance card both work well) — Home Assistant builds the card for you.

Repeat step 2 any time you've added new devices and want them on the card too — this "Add to dashboard" flow is native to Home Assistant, no custom cards or config files required. WireGuard entries never appear here, since they aren't monitored devices.

If you'd rather define the card yourself in YAML, two examples are included:

- [example.lovelace](example.lovelace) — a plain `entities` card listing specific entity IDs. No extra dependencies, but you add a line yourself each time you add a new device.
- [example.lovelace-auto](example.lovelace-auto) — an auto-populating card using the [auto-entities](https://github.com/thomasloven/lovelace-auto-entities) custom card (install it via HACS → Frontend first). It filters by `integration: ha_device_status`, so every device shows up automatically, with no editing required.

## Maintainers

- Jonathan Stoff
