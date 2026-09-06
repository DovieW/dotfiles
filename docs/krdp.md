# KRdp remote desktop

The `kubuntu-desktop` profile uses Plasma's native KRdp server as its preferred
interactive remote desktop. It deliberately does not enable SDDM autologin.
After a reboot, graphical access therefore becomes available after the user
logs into Plasma; ordinary key-only SSH remains available earlier.

Apply and inspect the managed server with:

```bash
dot apply --profile kubuntu-desktop --tags krdp
dot doctor --profile kubuntu-desktop
```

The server is bound to the active Tailscale IPv4 address on TCP 3389. UFW also
permits that port only on `tailscale0`. Authentication uses the current,
case-sensitive Linux username through PAM. The system password is entered into
the RDP client and is never stored in this repository or passed in a process
argument by the managed launcher.

Each connection streams the desktop's existing primary Plasma output. The
managed client fits that 16:9 workspace inside the laptop's 16:10 screen. KRdp's
virtual-monitor mode is deliberately not used: it creates an empty auxiliary
output rather than a complete interactive Plasma workspace. Because this is a
physical-session stream, activity can also be visible on the attached monitor.
The implementation uses the supported desktop-portal session path for remote
pointer and keyboard input.

A managed connection watcher changes every current Plasma panel from auto-hide
to always visible while KRdp is connected. It shares state with NoMachine,
survives Plasma panel ID changes, and restores the previous hiding modes only
after the final managed remote session disconnects.

Before opening the RDP connection, the managed client uses key-only SSH to
prepare the output's Plasma scale, changing it from its physical 145% setting
to 235%. KRdp records the logical screen dimensions when its Wayland portal
opens: changing scale afterward invalidates pointer mapping even when resolution
is unchanged. Scale therefore stays fixed throughout the connection. The
watcher restores the original scale on disconnect, and failed or abandoned
preparations expire after 60 seconds. The launcher also requests cleanup on exit.
The client needs working key-only SSH to the same host and Linux user as RDP.
Clients launched without this preparation use the output's existing scale.
FreeRDP's own DPI negotiation flags are omitted because KRdp ignores them for
the existing physical output and they can distort pointer mapping.

## Audio and microphone

KRdp 6.6.4 does not implement native RDP audio. The managed launcher therefore
starts a separate, two-way PipeWire audio bridge alongside FreeRDP:

- Desktop playback goes to the laptop's default output through
  `KRdp-Laptop-Speakers`.
- The laptop's default microphone becomes `KRdp-Laptop-Microphone` on the
  desktop. Laptop microphone mute settings remain effective.

Both paths use a private Unix socket forwarded through key-only SSH. There is
no new TCP audio listener, copied audio cookie, or saved audio recording. The
desktop and laptop must run PipeWire's PulseAudio-compatible service. The
server's `krdp` Ansible task installs the required `pactl` utility and bridge;
the client's `rdp` configuration installs the local lifecycle helper.

Existing desktop playback and recording streams are moved to the bridge, and
the bridge becomes the desktop's default output and input. Apps explicitly
pinned to another device may need `KRdp-Laptop-Microphone` selected in their own
settings. The laptop's normal local audio routes are not changed.

On disconnect, previous desktop defaults and per-stream routes are restored,
and both tunnels are removed. Manual device changes made during the session
are preserved. The helper is tied to the exact FreeRDP process and requires an
RDP connection from the same SSH peer; a heartbeat and the server watcher clean
up dropped connections or killed helpers. Audio retries independently if its
SSH link breaks, without restarting video or changing display scale.

This is an additional audio transport, not synchronized native RDP audio;
network buffering may affect lip sync. The tunnel target latency is 80 ms per
direction. Headphones are preferable for calls to avoid speaker feedback.

The implementation uses PipeWire's [tunnel sink](https://docs.pipewire.org/page_pulse_module_tunnel_sink.html)
and [tunnel source](https://docs.pipewire.org/page_pulse_module_tunnel_source.html).

## Client

On the managed laptop, launch **Desktop (KRdp)** from the application menu or
run:

```bash
krdp-client
```

The launcher deliberately uses Homebrew's FreeRDP build because Ubuntu's
FreeRDP package is built without the H.264 graphics support required by KRdp.
The managed Kubuntu package profile installs that client automatically.

The XFreeRDP client opens fullscreen, enables clipboard redirection, and
uses trust-on-first-use for the private self-signed certificate. The first
connection asks for the desktop's Linux username and password and may ask to
trust the certificate. NoMachine remains installed during initial acceptance
testing and can be retired after KRdp video, pointer, keyboard, clipboard,
scaling, reconnect, and post-reboot behavior are accepted.

The launcher permits only one KRdp client at a time. Two simultaneous clients
compete for the same Wayland clipboard, which can trigger repeated FreeRDP
format-conversion failures and crash CopyQ's clipboard monitor. A second launch
therefore explains that the existing KRdp window must be closed first.

KRdp is an existing-session server. It is not a replacement for SDDM and does
not create a separate Windows-style login session. KDE's upstream Plasma 6.6
documentation describes the same limitation:

<https://invent.kde.org/plasma/krdp/-/blob/Plasma/6.6/README.md>
