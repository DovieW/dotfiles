# Remapping laptop hardware keys on Plasma

Trace a physical key through the Linux input device, XKB, and Plasma before
changing a shortcut. An Fn combination can come from a vendor hotkey device
even when the same keycap's plain function key comes from the main keyboard.

## Find the event and any existing handler

1. Inspect `/proc/bus/input/devices` and `/dev/input/by-path/` for the built-in
   keyboard and any separate hotkey device. Resolve the event number on the
   machine you are working on. Check whether a remapper such as keyd grabs the
   device and forwards its events through a virtual keyboard.
2. Capture one physical press on the identified device. If installed, use
   `sudo evtest /dev/input/eventN` without grabbing the device. Look for
   `MSC_SCAN` and `EV_KEY`. For the live scan-code-to-key-code table, use the
   evdev `EVIOCGKEYCODE_V2` ioctl. A synthetic press can test Plasma's handling
   of a key code, but the physical press is what verifies the firmware path.
3. Check `udevadm info --query=property --name=/dev/input/eventN` for the live
   `KEYBOARD_KEY_*` properties and search the shipped
   `/usr/lib/udev/hwdb.d/` entries for that device. Some keys already trigger a
   kernel or desktop action. The IdeaPad airplane key originally emitted
   `KEY_RFKILL`, which could change radio state before Plasma ran a shortcut.

## Remap and activate the key

Use a udev hwdb override in [config/udev/hwdb.d](../config/udev/hwdb.d), scoped
to the input device name and hardware model. Match the spelling of a shipped
property exactly when overriding it. The kernel reads `0d` and `d` as the same
scan-code number. Hwdb distinguishes the full property names
`KEYBOARD_KEY_0d` and `KEYBOARD_KEY_d`.

Choose a spare Linux key code that produces a keysym in the active XKB layout.
Check `/usr/share/X11/xkb/keycodes/evdev` and
`/usr/share/X11/xkb/symbols/inet`. Qt accepting a shortcut name only proves
that it can parse the name. On this IdeaPad, an F24 binding registered in
Plasma even though the active XKB layout provided no usable F24 symbol.
`KEY_CONNECT` produced `XF86Go`, which Qt and Plasma recognize as **Go**.

The [managed IdeaPad task](../ansible/tasks/instant-connect-key.yml) builds the
database with `systemd-hwdb --strict update` and reloads udev with
`udevadm control --reload`. A database query can already show the new rule
while the running udev daemon still has the old one. Even after the kernel map
changes, Plasma's existing libinput device can still hold the old key
capabilities. A udev `change` event alone left the physical key silent in this
case. Reattaching just the hotkey device with udev `remove` then `add` events
fixed it without restarting Plasma.

To inspect the exact target before reattaching it, use the stable device link
and a dry run. This example is specific to the IdeaPad in this repository.

```sh
instant_key_device=/dev/input/by-path/pci-0000:00:1f.0-platform-VPC2004:00-event
instant_key_sysfs="/sys$(udevadm info --query=path --name="$instant_key_device")"
udevadm trigger --dry-run --verbose --action=remove "$instant_key_sysfs"
```

Once the output identifies only the intended extra-button event device, the
managed task can apply the remap and reattach it. For a manual reattach, run
`sudo udevadm trigger --action=remove --settle "$instant_key_sysfs"` and
`sudo udevadm trigger --action=add --settle "$instant_key_sysfs"` in that
order.

## Verify the Plasma shortcut

For an application launcher, set `X-KDE-Shortcuts` in its installed desktop
entry and refresh KDE's application cache with `kbuildsycoca6 --noincremental`.
Check the running session through KGlobalAccel. KDE discovered the shortcut
when the launcher was first installed. It retained the old F24 binding after
the desktop file was changed to Go. The
[launcher task](../ansible/tasks/connection-check.yml) migrates that exact
old binding through D-Bus so the live session uses the updated one.

```sh
# Qt key value 16777431 is Go.
busctl --user call org.kde.kglobalaccel /kglobalaccel \
  org.kde.KGlobalAccel getGlobalShortcutsByKey i 16777431
```

Use the physical key for the final test. If a simulated key or a direct
KGlobalAccel invocation works and the physical key produces the expected
`EV_KEY`, check that the compositor has reopened the device. For keys that
previously controlled radios, compare `rfkill list` or `nmcli radio all`
before and after the press.

## Verified Lenovo 83JM example

On the IdeaPad Pro 5 16IAH10, the `Ideapad extra buttons` device exposed two
airplane scan-code entries, `0d` and `13f`. The
[model-specific override](../config/udev/hwdb.d/90-instant-connect-ideapad.hwdb)
maps both to `KEY_CONNECT`. After reattaching the extra-button device, a
physical Fn+F8 press opened [Instant Connect](instant-wifi-connect.md) with
Wi-Fi and Bluetooth still on. Plain F8 comes from the main keyboard and
retains its usual function.
