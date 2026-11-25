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
  **Restart Bluetooth** is always visible. It checks for connected Bluetooth
  devices, then uses the desktop authorization prompt to restart the laptop's
  Bluetooth service. If you selected a device earlier, it retries that device
  after the restart.

Install with `bin/dot apply --profile kubuntu-laptop --tags connection-check`.

## Optional phone handoff

For one paired headset, Instant Connect can ask Tasker to pause the phone's
Bluetooth before connecting. Other phone Bluetooth accessories also disconnect
briefly. Create a Tasker HTTP Request event for `POST /7334` on port 7334, with
no quick response and a 10-second timeout. Set collision handling to
**Abort New Task** so a repeated request cannot interrupt Bluetooth restoration.
Give all four actions the same condition matching `%http_request_body` to a
private random token.

1. Run the Java Code below to request Bluetooth off through Tasker Settings.
   Enable **Continue Task After Error**.
2. Use HTTP Response with `%http_request_id`, status 200, and a text body of
   `%bt_connected`. Enable **Continue Task After Error** so a lost response
   cannot skip restoration. Instant Connect tries the laptop connection as
   soon as it receives `false`.
3. Wait 30 seconds.
4. Run Java Code to restore Bluetooth through Tasker Settings, verify
   `BluetoothAdapter.STATE_ON`, and retry once if needed.

On the S25 Ultra, Tasker's built-in Bluetooth actions could change the radio
state and then stall. These actions request the toggle through the same Tasker
Settings helper and check Android's public adapter state without waiting for
the helper's callback. They use Tasker Settings 2.0.

```java
adapter = android.bluetooth.BluetoothAdapter.getDefaultAdapter();
pkg = "com.joaomgcd.taskersettings";
request = new android.content.Intent();
request.setClassName(pkg, pkg + ".ServiceBackCompat");
request.putExtra(pkg + ".EXTRA_TYPE", "ToggleBluetooth");
request.putExtra(pkg + ".EXTRA_INPUT", "{\"value\":false}");
request.putExtra(pkg + ".EXTRA_PLUGIN_RECEIVER",
    (android.os.Parcelable) new android.os.ResultReceiver((android.os.Handler) null));
context.startService(request);
for (int i = 0; i < 30 && adapter.getState() != 10; i++) {
    Thread.sleep(100);
}
tasker.setVariable("bt_connected", adapter.getState() != 10);
```

For the restore action, repeat the setup through `EXTRA_PLUGIN_RECEIVER` with
`{"value":true}` as the input payload. Then run:

```java
for (int attempt = 0; attempt < 2 && adapter.getState() != 12; attempt++) {
    context.startService(request);
    for (int i = 0; i < 30 && adapter.getState() != 12; i++) {
        Thread.sleep(100);
    }
}
if (adapter.getState() != 12) {
    tasker.showToast("Phone Bluetooth did not turn back on.");
}
```

Set `~/.config/instant-connect/phone-handoff.json` (or its equivalent under
`XDG_CONFIG_HOME`) to a private JSON file with `host` (the phone's full
Tailscale MagicDNS name), `device` (the headset address), and `token` (the
same value used in Tasker). Keep the file mode at 0600. After handoff fails,
**Try laptop connection anyway**
retries the selected device without making another request to the phone. This
is useful if you manually disconnected the earbuds in the phone's Bluetooth
settings and Tasker still reports a link.
