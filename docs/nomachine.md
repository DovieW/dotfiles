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

Inside a session, open the NoMachine menu and select **Display**. Enable the
option that changes the remote display resolution to match the client window.
NoMachine's Wayland support requires an attached, active physical display and
does not automatically lock Plasma when the remote client disconnects. The
managed setup enables NoMachine EGL capture because its DRM and compositor
fallbacks do not capture Plasma Wayland reliably. Reboot once after the first
installation so Plasma starts with NoMachine's EGL interposer available.

The package version and SHA-256 are pinned in `ansible/tasks/nomachine.yml`.
Update both only after checking the release and provider-published digest on
the official NoMachine download page, then calculating the package SHA-256.
