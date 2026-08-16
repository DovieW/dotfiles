# NoMachine remote desktop

The native Kubuntu profile installs the free NoMachine edition for responsive
access to the existing Plasma Wayland desktop. It mirrors the physical session,
but can adapt that desktop to the client window instead of stretching a fixed
capture. MeshCentral remains installed for management, terminal, and file
access.

NoMachine is private to the tailnet:

- the NX daemon binds only to the laptop's active Tailscale IPv4 address;
- the host firewall permits NX TCP and UDP only through `tailscale0`;
- normal LAN SSH remains allowed while unsolicited inbound traffic is denied;
- LAN discovery, NoMachine Network, and UPnP router mapping are disabled;
- no NoMachine account or subscription is required; and
- the connection uses NoMachine's encrypted NX protocol on port 4000.

Install or repair it with:

```bash
dot apply --profile kubuntu-laptop --tags nomachine
```

On a new workstation, the main bootstrap safely defers NoMachine when Tailscale
has not been enrolled yet. Complete the one-time browser flow first, then apply
the deferred component:

```bash
sudo tailscale up
dot apply --profile kubuntu-laptop --tags nomachine
```

NoMachine is not installed before enrollment because its listener cannot be
restricted to a Tailscale address until that address exists.

Install the NoMachine client on the connecting computer and connect to the IP
shown by `tailscale ip -4`, port `4000`, using this laptop's normal Linux
username and password. Both computers must be connected to the tailnet.

The managed node hooks adapt the physical Plasma desktop automatically. When a
NoMachine session starts or reconnects, the single attached display switches to
1920x1200 at 115% scaling. That produces a 16:10, approximately 1670x1043
logical workspace closely matching the managed laptop's 1646x1029 workspace.
The lower 16:10 mode is intentional: the attached 4K display and AMD driver
advertise but reject the higher 2560x1600 mode. The exact pre-connection mode
and scale are saved and restored after the last session
disconnects or closes. Resize events reassert the remote mode, avoiding
Wayland's unreliable physical-desktop resizing behavior.

Plasma panels are also changed from auto-hide to always visible while a remote
session is active, so the task manager remains accessible at the remote screen
edge. Each panel's previous hiding mode is restored with the display state.

The physical monitor and its local keyboard and mouse remain active while a
remote session is connected. NoMachine's native blanking is disabled because
it blocks local input and is unreliable on Plasma Wayland. KDE brightness
dimming is also intentionally avoided because it darkens the remotely captured
image. `EnableLockScreen` still protects the workstation after disconnect.

On a Plasma client whose active display scale is at least 150%, the managed
launcher runs NoMachine inside Gamescope. It renders the complete legacy client
at two-thirds of the panel's native dimensions and scales the result by 1.5,
covering fonts, icons, buttons, menus, and the remote canvas consistently. On
the managed 2880x1800 laptop this is a 1920x1200 inner surface, which also
matches the desktop's remote mode. Lower-density clients launch NoMachine
directly without Gamescope.

The client launcher also starts a microphone guard. It mutes PipeWire capture
streams created by `nxplayer.bin`, preventing accidental room-audio forwarding
and feedback, while leaving the remote computer's playback stream enabled.

The hook deliberately exits successfully even when KScreen is unavailable so
a display problem can never prevent remote login. Its state and diagnostic log
are in `~/.local/state/dotfiles/nomachine-display.json` and
`~/.local/state/dotfiles/nomachine-display.log`. Check the live state with:

```bash
/usr/local/libexec/nomachine-display status
```

NoMachine's Wayland support requires an attached, active physical display and
does not automatically lock Plasma when the remote client disconnects. The
managed setup enables NoMachine EGL capture because its DRM and compositor
fallbacks do not capture Plasma Wayland reliably. Reboot once after the first
installation so Plasma starts with NoMachine's EGL interposer available.

The package version and SHA-256 are pinned in `ansible/tasks/nomachine.yml`.
Update both only after checking the release and provider-published digest on
the official NoMachine download page, then calculating the package SHA-256.
