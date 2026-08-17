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

Each connection creates a 2880×1800 virtual Plasma output at 175% scaling. This
matches the managed laptop's native panel and keeps the remote workspace off
the desktop's physical monitor. The implementation intentionally uses KRdp's
portal session rather than the more experimental `--plasma` path.

On the managed laptop, launch **Desktop (KRdp)** from the application menu or
run:

```bash
krdp-client
```

The launcher deliberately uses Homebrew's FreeRDP build because Ubuntu's
FreeRDP package is built without the H.264 graphics support required by KRdp.
The managed Kubuntu package profile installs that client automatically.

The FreeRDP SDL client opens fullscreen, enables clipboard redirection, and
uses trust-on-first-use for the private self-signed certificate. The first
connection asks for the desktop's Linux username and password and may ask to
trust the certificate. NoMachine remains installed during initial acceptance
testing and can be retired after KRdp video, pointer, keyboard, clipboard,
scaling, reconnect, and post-reboot behavior are accepted.

KRdp is an existing-session server. It is not a replacement for SDDM and does
not create a separate Windows-style login session. KDE's upstream Plasma 6.6
documentation describes the same limitation:

<https://invent.kde.org/plasma/krdp/-/blob/Plasma/6.6/README.md>
