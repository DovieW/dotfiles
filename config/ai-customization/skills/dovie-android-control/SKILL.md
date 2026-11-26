---
name: dovie-android-control
description: Use ADB or scrcpy with Dovie's Galaxy S25 Ultra when Dovie explicitly requests a phone operation.
---

# Dovie's Android phone

The phone's Tailscale MagicDNS name is `galaxy-s25u.barn-chameleon.ts.net`. Use the computer where Dovie wants ADB or scrcpy to run.

1. Ask Dovie to enable Android **Wireless debugging** and give the current connection port shown on that screen. If pairing is needed, ask for the separate port from **Pair device with pairing code**. Have Dovie enter the temporary code interactively in `adb pair <host>:<pairing-port>`. Pairing and connection ports can change.
2. Try `adb connect <host>:<connection-port>` using the full MagicDNS name unless Dovie supplies another verified address. Tailscale reachability alone does not prove Android's Wireless debugging listener is reachable. If the port fails, recheck the displayed port and Wireless debugging state. Android's documented same-Wi-Fi pairing path is a fallback if the tailnet path fails.
3. Check `adb devices -l` and confirm the exact connected serial before running device commands. Use `adb -s <serial> …` or `scrcpy --serial <serial>` so another attached device cannot receive the action.

Keep the pairing code, ADB keys, captures, and device output out of tracked files. Use only the phone actions Dovie requested.

[Android Wireless debugging](https://developer.android.com/tools/adb#connect-to-a-device-over-wi-fi)
