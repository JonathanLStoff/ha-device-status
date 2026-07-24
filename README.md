# ha-device-status
Home Assistant integration that monitors devices by checking ping reachability, TCP ports, or MQTT topics and exposing the result as binary sensors.

[![GitHub Release](https://img.shields.io/github/release/JonathanLStoff/ha-device-status.svg?style=flat-square)](https://github.com/JonathanLStoff/ha-device-status/releases)
[![License](https://img.shields.io/github/license/JonathanLStoff/ha-device-status.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-default-orange.svg?style=flat-square)](https://hacs.xyz)

## What it does

This integration creates one binary sensor per device you want to monitor. Each device can be checked one of these ways:

- Ping an IP address (optionally over a specific interface)
- Check whether a TCP port is open — optionally through a WireGuard tunnel this integration manages itself
- Subscribe to an MQTT topic and compare the payload to an expected value

WireGuard tunnels run **entirely in Python**, via the [wireguard-requests](https://github.com/bshuler/wireguard-requests) package (Cloudflare's boringtun + a userspace TCP/IP stack, via Rust bindings) — no system network interface, no `wireguard-tools`/`wg-quick`, no `NET_ADMIN` capability, nothing to install at the OS level. This is what makes it usable on Home Assistant OS, where installing system packages isn't possible. The tradeoff: only TCP is supported (no ICMP), so a WireGuard-routed "ping" device does a TCP-connect check rather than a real ping — see below.

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
   - `ping` — IP/hostname, attempt count, timeout, and an **interface** you pick from a dropdown (any WireGuard tunnel you've already added through this integration shows up as an option, the same way notify services do below — or type your own interface name to bind the system `ping` to some other, externally-managed interface). Picking a WireGuard tunnel switches this to a TCP-connect check, so a **port** becomes required too (WireGuard-in-Python has no ICMP support).
   - `port` — IP/hostname and port, plus an optional **interface** to route the connection through one of your WireGuard tunnels.
   - `mqtt` — topic and expected payload.
   - `wireguard` — see "Adding a WireGuard tunnel" below. This isn't a monitored device (no binary sensor); it exists so it can be selected as the "interface" for `ping`/`port` devices.
3. **Notifications & schedule** *(skipped for `wireguard`)* — pick which `notify.*` services (e.g. your phone's Home Assistant companion app) should be alerted for *this device*, whether to also notify on recovery, and the cron schedule for how often it's checked.

Repeat "Add Integration" for each additional device — every device is its own entry with its own notification routing and schedule. To change a device's notify services/schedule, or a WireGuard tunnel's connection details, click **Configure** on that entry in Devices & Services.

To route notifications to a phone, install the [Home Assistant companion app](https://www.home-assistant.io/companion-app/) on it first — its `notify.mobile_app_<device>` service will then show up as an option in the flow.

### Adding a WireGuard tunnel

Add a device with type `wireguard` to have the integration establish the tunnel itself — entirely in Python, no system interface, either:

- **From an existing config**: set "Existing wg-quick config file path" to a `wg-quick`-style `.conf` file. Either an absolute path (e.g. `/etc/wireguard/wg0.conf`) or a path relative to your Home Assistant config directory (e.g. `wireguard/wg0.conf`, resolving to `/config/wireguard/wg0.conf`) works.
- **Inline**: leave the config path blank and fill in address, private key, and the peer's public key, endpoint, and allowed IPs (keepalive and preshared key are optional). This models a single-peer client setup — the common case of connecting out to one VPN server.

Unlike a real `wg-quick`-managed interface, there's no OS-level name for this tunnel — it's referred to by the **device name** you gave it in the first step. Pick that name from the "interface" dropdown when adding a `ping` or `port` device to route its check through the tunnel.

**Limitations, since this is a userspace TCP/IP implementation rather than a real network interface:**

- **No ICMP.** A `ping` device routed through a WireGuard tunnel does a TCP-connect check instead of a real ping, so it needs a port set.
- **Only reaches things through this tunnel.** Other integrations, and Home Assistant itself, are unaffected — this tunnel exists only for the specific devices you point at it, not systemwide.
- **This is an early-stage dependency.** [wireguard-requests](https://github.com/bshuler/wireguard-requests) is a young, low-adoption package. If you'd rather rely on the real, upstream WireGuard implementation, terminate the tunnel outside Home Assistant (on your router, a Proxmox host, etc.) and just add the remote device as a plain `ping`/`port` device with no `interface` set — this is also the only real option on Home Assistant OS, where installing arbitrary system packages isn't possible at all.
- **Python 3.14:** as of writing, this package has no prebuilt wheel for Python 3.14, only up to 3.13. If your Home Assistant runs Python 3.14 and your platform can't build the Rust extension from source (no Rust toolchain — true of essentially all stock Home Assistant containers/HAOS), installing this integration's requirements will fail entirely, not just the WireGuard feature. Check `python3 --version` in your Home Assistant environment before relying on this.

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

    - name: "Remote NAS"         # only reachable over the WireGuard tunnel
      type: ping
      ip: 10.0.0.5
      interface: wg0             # route through the tunnel named "wg0" below
      port: 22                   # required for WireGuard-routed ping (TCP check, no ICMP)

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
| `wireguard` | top level | Optional. Have the integration establish a WireGuard tunnel itself (in-process, no system interface). See below. |
| `cron` | top level | Cron expression for how often ping/port devices are checked. Default `*/1 * * * *` (every minute). |
| `notify_services` | top level | List of Home Assistant companion-app notify services (e.g. `mobile_app_johns_iphone`). Find yours under **Developer Tools → Actions**. |
| `notify_online` | top level | If `true`, also push a notification when a device comes back online. Default `false`. |
| `notify_offline` | top level | List of item names that should trigger notifications when offline. |
| `interface` | per ping/port item | Name of a WireGuard tunnel (the `wireguard.interface` value below) to route this check through. For `ping`, this switches to a TCP-connect check and requires `port`, since there's no ICMP support. |
| `count` | per ping/port item | Number of attempts. Default `2`. |
| `timeout` | per ping/port item | Per-attempt timeout in seconds. Default `3`. |

**Notifying phones:** each phone with the Home Assistant companion app exposes a `notify.mobile_app_<device>` service. List those service names (without the `notify.` prefix) under `notify_services`, and list which devices should trigger alerts under `notify_offline`.

**WireGuard tunnel:** the `wireguard` block establishes the tunnel entirely in Python via [wireguard-requests](https://github.com/bshuler/wireguard-requests) — no system network interface, no `wireguard-tools`, no `NET_ADMIN`, nothing to install at the OS level. Either point at an existing wg-quick config file (`config_path`, absolute or relative to your Home Assistant config directory), or supply `private_key`/`address`/`peers` inline. `interface` here is just a label other items reference via their own `interface:` field — there's no real OS interface being named. See the top of this README for the TCP-only/no-ICMP limitation and the current Python 3.14 wheel gap for this dependency.

If you use MQTT-based checks, make sure the MQTT integration is configured in Home Assistant.

## Dashboard status card

Every monitored device (ping/port/mqtt) you add through the UI gets its own Home Assistant device and entity under **Settings → Devices & Services → Device Status**. To add a status card for all of them at once, entirely through the UI, no YAML at all:

1. Go to **Settings → Devices & Services → Entities**.
2. Use the filter sidebar to filter by **Integration: Device Status**. This lists every monitored device's entity (WireGuard entries never appear here, since they aren't monitored devices and have no entity).
3. Select them all (checkbox in the header selects every filtered row), then click **Add to dashboard** in the action bar that appears.
4. Choose a dashboard/view and a card type (Entities or Glance both work well) — Home Assistant builds the card for you.

Repeat any time you've added new devices and want them included — this is Home Assistant's native entity management UI, no custom cards or config files required. You can also open a single device's page (via its entity, or under the **Devices** tab) and use the **Add to dashboard** button there for just that one device.

If you'd rather define the card yourself in YAML, two examples are included:

- [example.lovelace](example.lovelace) — a plain `entities` card listing specific entity IDs. No extra dependencies, but you add a line yourself each time you add a new device.
- [example.lovelace-auto](example.lovelace-auto) — an auto-populating card using the [auto-entities](https://github.com/thomasloven/lovelace-auto-entities) custom card (install it via HACS → Frontend first). It filters by `integration: ha_device_status`, so every device shows up automatically, with no editing required.

## Maintainers

- Jonathan Stoff
