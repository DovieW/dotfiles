# Instant Connect

Search the Start menu for **Instant Connect**, then choose Wi-Fi or Bluetooth.

- **Wi-Fi** scans and activates the selected saved NetworkManager profile. This
  can switch the active Wi-Fi connection. Add future choices to `NETWORKS` in
  the script using saved profile UUIDs from `nmcli connection show`.
- **Bluetooth** lists devices already paired in System Settings. Select a device
  and press Connect to request a normal BlueZ connection. Use Refresh devices
  after pairing another device. If a connection fails, the launcher shows the
  BlueZ error and lets you try again.

Install with `bin/dot apply --profile kubuntu-laptop --tags connection-check`.
