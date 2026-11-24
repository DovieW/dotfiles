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
