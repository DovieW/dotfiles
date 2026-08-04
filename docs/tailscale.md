# Tailscale

## Ownership

Kubuntu uses Tailscale's official stable Ubuntu APT repository. Dotfiles
validates the repository signing-key fingerprint, installs the latest stable
package, and enables the `tailscaled` system service.

Windows records `Tailscale.Tailscale` in its inventory-only Winget manifest.
The Windows adapter does not install it automatically.

The personal and work WSL profiles do not install another Tailscale client.
[Tailscale recommends using the Windows host client](https://tailscale.com/docs/install/windows/wsl2)
because running both can nest encrypted traffic and prevent WSL connectivity.

## First enrollment

Apply the Kubuntu role:

```bash
dot apply --profile kubuntu-laptop --tags tailscale
```

The package and daemon are reproducible, but tailnet membership is deliberately
local machine state. Join the machine once:

```bash
sudo tailscale up
```

Open the URL printed by the command and authenticate in the browser. No
reusable auth key, session, node key, or Tailscale state is committed or stored
in Bitwarden by this workflow.

This follows Tailscale's documented
[Linux installation and enrollment flow](https://tailscale.com/docs/install/linux).

Verify the result:

```bash
tailscale status
tailscale ip
dot doctor --profile kubuntu-laptop
```

Normal `dot update --profile kubuntu-laptop` runs keep the package on the
latest stable repository candidate without changing enrollment or tailnet
options.

## Administration OAuth client

Homelab inventory and policy automation uses a narrowly scoped OAuth client
stored in the Bitwarden secure note `dotfiles/tailscale-oauth`. Store or rotate
it interactively:

```bash
dot secrets tailscale-oauth
```

The resulting one-hour access token exists only in the explicit homelab
process. It is never loaded by shell startup or persisted to disk. Successful
OAuth migration moves the superseded `dotfiles/tailscale-api` user token to
Bitwarden trash.

The command unlocks Bitwarden only for its own process, validates the OAuth
client against the Tailscale API, stores it without placing it in a process
argument, and locks the CLI vault afterward. The credentials must never be exported from
`.zshrc`, `.bashrc`, or another startup file.

## Policy

Dotfiles does not automatically enable Tailscale SSH, advertise routes, use an
exit node, change DNS acceptance, or disable key expiry. Those choices affect
tailnet security and routing and should be made deliberately after the basic
client is working.
