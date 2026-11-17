# Instant Wi-Fi Connect

Apply with `bin/dot apply --profile kubuntu-laptop --tags connection-check`.
Search the Start menu for **Instant Wi-Fi Connect**. Choose a network and click
Connect to request a scan and activate its saved NetworkManager profile. Selecting
another network can switch the active Wi-Fi connection. The scan cannot make an
offline hotspot available. Add future choices to `NETWORKS` in the script using
saved profile UUIDs (`nmcli connection show`).
