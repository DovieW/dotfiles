# Instant Connect

Search the Start menu for **Instant Connect**. Click a Wi-Fi network or paired
Bluetooth device to connect immediately.

- **Wi-Fi** scans and activates the selected saved NetworkManager profile. This
  can switch the active Wi-Fi connection. Add future choices to `NETWORKS` in
  the script using saved profile UUIDs from `nmcli connection show`.
- **Bluetooth** lists devices already paired in System Settings. Use Refresh
  devices after pairing another device. If the first attempt fails, the launcher
  clears the selected device's connection and retries. If Bluetooth stays busy,
  it backs off briefly, then can power-cycle the laptop adapter once if it has
  no connected devices, discovery, discoverability, or active LE advertisements.
  For devices that advertise stereo playback, it can also try A2DP directly.
  Pairings are preserved. If recovery fails, the launcher shows the errors.

Install with `bin/dot apply --profile kubuntu-laptop --tags connection-check`.

## Optional phone handoff

For one paired headset, Instant Connect can ask Tasker to release it from the
phone before connecting. Create a Tasker HTTP Request event for `POST /7334`
on port 7334, with no quick response and a 10-second timeout. The task should
use Bluetooth Connection → Disconnect for that headset with a 2-second
timeout and **Continue Task After Error** enabled, then Bluetooth Info →
Single Device for the same address.
Scope the disconnect and HTTP Response
actions to requests whose `%http_request_body` matches a private random token.
Have HTTP Response use `%http_request_id`, status 200, and a text body of
`%bt_connected`. The launcher proceeds only on a successful response of
`false`.

Set `~/.config/instant-connect/phone-handoff.json` (or its equivalent under
`XDG_CONFIG_HOME`) to a private JSON file with `host` (the phone's full
Tailscale MagicDNS name), `device` (the headset address), and `token` (the
same value used in Tasker). Keep the file mode at 0600. The phone's Bluetooth
radio remains enabled. After handoff fails, **Try laptop connection anyway**
retries the selected device without making another request to the phone. This
is useful if you manually disconnected the earbuds in the phone's Bluetooth
settings and Tasker still reports a link.
