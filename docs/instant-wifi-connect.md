# Instant Connect

Search the Start menu for **Instant Connect**, then choose Wi-Fi or Bluetooth.

- **Wi-Fi** scans and activates the selected saved NetworkManager profile. This
  can switch the active Wi-Fi connection. Add future choices to `NETWORKS` in
  the script using saved profile UUIDs from `nmcli connection show`.
- **Bluetooth** lists devices already paired in System Settings. Use Refresh
  devices after pairing another device. Select a device and press **Force
  Connect**. If the first attempt fails, the launcher clears the selected
  device's connection and retries. For devices that advertise stereo playback,
  it can then try the A2DP profile directly. Pairing is preserved and the
  Bluetooth adapter stays on. If recovery fails, the launcher shows the errors.

Install with `bin/dot apply --profile kubuntu-laptop --tags connection-check`.
