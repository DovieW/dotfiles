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

The same watcher temporarily changes the desktop's 4K Plasma output from its
physical 145% scale to 235% while KRdp is connected. After FreeRDP reduces the
3840x2160 stream to fit the laptop, controls and text therefore have roughly
the laptop's native 175% apparent size. The original physical scale is recorded
before the first adjustment and restored when the connection closes. This is
done through `kscreen-doctor` because KRdp does not apply FreeRDP's requested
desktop-scale capability to the existing Wayland output. The watcher waits for
actual video traffic before changing the scale; applying it during TCP or PAM
setup is too early for KRdp's portal capture to observe the resize.

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

KRdp is an existing-session server. It is not a replacement for SDDM and does
not create a separate Windows-style login session. KDE's upstream Plasma 6.6
documentation describes the same limitation:

<https://invent.kde.org/plasma/krdp/-/blob/Plasma/6.6/README.md>
