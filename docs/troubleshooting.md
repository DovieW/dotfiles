# Troubleshooting

## Bitwarden is unavailable

Run `bw status`. If it reports unauthenticated, run `bw login` once. Do not add
`BW_SESSION` to `.bashrc`, `.zshrc`, an env file, or this repository.

If this is the first machine and the bootstrap Secure Note does not exist, run:

```bash
dot secrets initialize --draft ~/.config/dotfiles/bootstrap-draft.json
```

Initialization refuses to overwrite an existing note.

## GitHub registration is pending

Install GitHub CLI, authorize both SSH key-management scopes, and rerun:

```bash
gh auth login -h github.com -p ssh -w \
  -s admin:public_key,admin:ssh_signing_key
```

```bash
dot secrets sync --profile PROFILE
```

The public key remains safely stored even if registration could not run.

## Homebrew is missing

Ansible stops before attempting Brew-owned packages and links no partial
package state. Install Homebrew from its official installer and rerun apply.

## Segoe UI Variable is skipped

Mount a Windows installation containing `Windows/Fonts/SegUIVar.ttf`, then run
`scripts/provision-segoe`. The font is copied to the user font directory and is
never stored in Git.

## KDE or Plasma is wrong

List backups under `~/.local/state/dotfiles/backups`, then run:

```bash
dot rollback RUN_ID
```

### KDE apply refuses local drift

This means an allowlisted KDE file changed through System Settings or an
application after its last deployment. Review it before choosing a direction:

```bash
dot diff kde
dot capture kde --only NAME
```

Use `dot apply --profile kubuntu-laptop --force-kde` only when the committed
repository copy should intentionally replace the live file. The replaced file
is backed up for rollback.

Log out and back in after restoring panel or shortcut configuration. Portable
setup never replaces KScreen topology. Repair the Kubuntu laptop's separately
managed internal-display policy without touching geometry:

```bash
dot apply --profile kubuntu-laptop --tags display
dot doctor --profile kubuntu-laptop
```

The display action identifies the built-in Samsung OLED by EDID, temporarily
mounts the `Windows-SSD` volume read-only when necessary, copies Lenovo's
factory ICC profile, and unmounts a volume it mounted itself. If Windows is
unavailable, the action reports a clear skip rather than installing a generic
or incorrect profile. Adaptive Sync is intentionally disabled: fixed 120 Hz
prevents uneven pointer motion in fullscreen Chromium and Electron windows.

### A taskbar profile does not match its description

Inspect the selected and live state:

```bash
dot panel status
dot diff kde
```

Use `dot panel use windows-classic` to rebuild the baseline. The named profile
is authoritative: switching reconstructs its exact widget order, prints a
rollback ID, and leaves Plasma-generated containment IDs host-local.

### A downloaded `.rdp` file does not open

Repair the client, MIME database, desktop entry, and default association:

```bash
dot apply --profile kubuntu-laptop --tags rdp
dot doctor --profile kubuntu-laptop
```

Both `.rdp` and Azure `.rdpw` files should report the MIME type
`application/x-rdp` or Ubuntu's competing `application/x-remmina` type. Both
MIME defaults intentionally point to the extension-aware managed dispatcher;
native `.remmina` profiles still delegate directly to Remmina.

Ordinary downloads open fullscreen in stock SDL FreeRDP. F5-style downloads
with `gatewayaccesstoken` use the restored Remmina workflow, which avoids SDL's
local target-credential form without patching FreeRDP. The generated Remmina
profile exists only in the per-user runtime directory, is readable only by the
user, and is erased after Remmina has consumed it. Certificate validation
remains enabled.

At each launch, the managed Remmina helper queries KScreen for the primary
display's current physical canvas and Plasma scale. It has Windows render at
that same desktop scale while selecting FreeRDP's closest supported 100%, 140%,
or 180% device bucket. This follows monitor and scaling changes without another
`dot apply` and keeps text pixel-sharp. If KScreen is unavailable, it falls back
to the managed laptop's 2880×1800 canvas at 175% scale. The launcher deliberately
relies on profile `viewmode=4`
rather than passing Remmina's `--enable-fullscreen` flag: that flag makes GTK
replace the custom canvas with its approximately 1644×1028 logical surface,
which looks correctly sized but fuzzy when stretched over the physical panel.
Dynamic resolution remains disabled.

The ephemeral profile starts with keyboard grabbing enabled, so ordinary
desktop shortcuts are sent to remote Windows; tapping Right Control releases
or restores the grab. The fullscreen toolbar is disabled completely, including
its edge-hover activation area. Managed Right Control shortcuts use `V` to send
the local clipboard as keystrokes, `M` to minimize Remmina, and `F9` to toggle
view-only mode. Standard bidirectional RDP clipboard redirection is also
enabled; the keystroke command remains available as a fallback for targets or
fields where clipboard redirection does not work.
Closing a window containing multiple connections does not show an additional
confirmation prompt.
Right Control+F12 saves a local screenshot and also places the image on the
local clipboard for immediate pasting.

The generated profile selects Remmina's Best quality preset, and dotfiles
manages that preset with FreeRDP's font-smoothing flag enabled. If remote text
looks jagged after an update, reconnect the RDP session and verify that
`rdp_quality_9=80` remains in `~/.config/remmina/remmina.pref`.

F5 launch tokens are short-lived and may be single-use. If a launch was
interrupted or used for diagnostics, download a fresh `.rdp` file before
retrying.

## The lock screen is blank, stock, or still shows media

Preview the managed package without actually locking:

```bash
dot lockscreen preview
```

Then restore its package, wallpaper, and correct `[Greeter][LnF]` setting:

```bash
dot apply --profile kubuntu-laptop --tags lockscreen
dot doctor --profile kubuntu-laptop
```

The custom QML omits media controls entirely. KDE's stock fallback also reads
`showMediaControls=false` from the `LnF` subgroup; placing the key directly
under `[Greeter]` has no effect. Use `dot lockscreen stock` to select KDE's
complete stock shell while diagnosing a Plasma compatibility problem.

After a rejected password, the managed theme mirrors KScreenLocker's stock
three-second retry lifecycle: it clears the rejected secret and restarts the
authenticator when the grace period expires. Unlike the stock field, it remains
editable during that interval: pressing Enter queues the new password in memory
and submits it as soon as authentication is ready. The queued secret is never
written to disk. If the field remains unresponsive for longer than three
seconds, reapply the `lockscreen` tag before investigating PAM; an older managed
theme could leave the authenticator stopped indefinitely.

## Closing the lid suspends the laptop

The managed policy ignores lid closure and disables automatic suspend for AC,
battery, and low-battery profiles. It preserves manual Sleep and the physical
power button. While closed, the managed user service selects power-saver to
reduce heat and power draw; it restores the appropriate AC or battery profile
and explicitly asks PowerDevil to wake the display when the lid opens. Apply
the live PowerDevil policy, lid controller, and system fallback:

```bash
dot apply --profile kubuntu-laptop --tags kde
```

To repair only the event-driven lid controller without replacing KDE state or
requiring administrator access:

```bash
dot apply --profile kubuntu-laptop --tags power
```

Verify both no-sleep behavior and the current lid-aware power choice with:

```bash
dot doctor --profile kubuntu-laptop
```

This is not a substitute for suspend: manually sleep the laptop before putting
it in a bag.

## Custom touchpad gestures fail or destabilize KWin

Check the managed build, configuration, and live effect:

```bash
dot gestures status
```

For an ordinary configuration problem, restore the tracked YAML and reload it:

```bash
dot apply --profile kubuntu-laptop --tags gestures
dot gestures reload
```

The gesture-only apply path manages only InputActions and its KWin enable flag.
Unrelated KDE settings drift does not block it.

For immediate recovery, hold Backspace, Space, and Enter together for two
seconds, or disable the KWin effect:

```bash
dot gestures disable
```

That command deliberately changes the live `kwinrc`, so KDE drift is expected
until `dot gestures enable` or the gesture profile is reapplied. If KWin itself
was just upgraded, log out and back in before re-enabling the plugin; it is
compiled against the installed KWin version and cannot safely replace a shared
library already loaded by the running compositor.

## The touchpad intermittently ignores motion

Check for libinput's jump detector:

```bash
journalctl --user -b | grep "Touch jump detected and discarded"
dot doctor --profile kubuntu-laptop
```

The CIRQ1080 touchpad can deliver regular I2C reports in a burst. libinput
1.31.1 may normalize the short arrival interval into an impossible movement
and discard it, which feels like a missed touch or a brief stop. The Kubuntu
profile installs a quirk scoped to the Lenovo 83JM and exact touchpad identity:

```bash
dot apply --profile kubuntu-laptop --tags touchpad
```

Log out and back in after applying because KWin creates its libinput context at
session startup. The workaround disables jump detection; it does not alter the
tracked flat pointer profile or the intentionally low scroll factor. If the
cursor begins making visible jumps, restore the previous behavior by removing
`/etc/libinput/local-overrides.quirks`, then log out and back in. Remove the
tracked workaround once the fix for upstream libinput issue #1297 ships in
Ubuntu.

## A graphical Git client cannot find the private signing key

Kubuntu deliberately stores only the public device key under `~/.ssh`; the
private key remains in Bitwarden. Confirm Bitwarden Desktop is running,
unlocked, and has its SSH agent enabled. Then verify the managed desktop
environment and restart the affected graphical application completely:

```bash
systemctl --user show-environment | grep SSH_AUTH_SOCK
SSH_AUTH_SOCK="$HOME/.bitwarden-ssh-agent.sock" ssh-add -L
```

The first command should report
`SSH_AUTH_SOCK=$HOME/.bitwarden-ssh-agent.sock`. Existing graphical processes
retain the environment with which they started, so reloading a vault or plugin
is not sufficient after correcting the session agent. The Kubuntu profile
masks Ubuntu's competing `ssh-agent.socket`; `dot doctor` verifies both that
mask and the Bitwarden route. Managed Obsidian launchers additionally set the
socket explicitly, but an Obsidian process that predates the fix must still be
fully quit and reopened once.

Enter the administrator password when prompted. PowerDevil is restarted only
when its managed configuration changes. The systemd-logind fallback is
guaranteed after the next reboot. Verify both layers with `dot doctor`.

## NVIDIA is still using Nouveau

Apply the dynamically recommended Ubuntu desktop driver and reboot:

```bash
dot apply --profile kubuntu-laptop --tags gpu
sudo reboot
```

The role follows the package marked `recommended` by `ubuntu-drivers` and sets
PRIME on-demand. After reboot, verify the loaded driver, PRIME mode, and the
rest of the workstation with `dot doctor --profile kubuntu-laptop`.

On the IdeaPad Pro 5 16IAH10 with PZCN55WW firmware, driver 595.84's optional
`nvidia-powerd` Dynamic Boost daemon crashes while reading SBIOS power data.
The Kubuntu profile disables that daemon to prevent repeated crash reports.
Normal NVIDIA acceleration and runtime D3 battery savings remain enabled. A
future driver or firmware update should be tested before removing the
workaround.

## Shell startup is slow

Profile Zsh with:

```bash
PROFILE_ZSH_STARTUP=1 zsh -i -c exit
```

## Vite+ is missing or `vp env use` does not persist

Run:

```bash
scripts/install-vite-plus --check
vp env setup --env-only
```

Then open a new shell and run `vp env doctor`. Do not manually add Vite+
installer lines to `.bashrc` or `.zshrc`; dotfiles sources the generated
`$VP_HOME/env` file after shell completion initialization.

Use `mbash` for an intentionally minimal shell and `fullbash` to switch back to
the complete Bash profile. Minimal mode is visibly labeled `[mbash]` and keeps
its prompt static. Full Bash uses a two-line prompt with the current directory,
Git branch when applicable, and the previous command's nonzero exit status.

## Package updates fail before the first APT task

Interactive `dot apply` and `dot update` runs tell Ansible to request its become
password before the play starts. Ansible then supplies that password directly
to each privileged task instead of depending on a terminal-specific sudo
timestamp. Noninteractive runs require passwordless sudo or stop before the
play with an instruction to retry in a terminal.

Ubuntu 26.04 supplies `sudo-rs`, whose PAM prompt wraps the custom token passed
by Ansible. `dot` detects `/usr/lib/cargo/bin/sudo` and selects the repository's
`sudo_rs` become plugin so Ansible recognizes that wrapped prefix. Other Linux
systems continue using Ansible's standard `sudo` plugin.

## Docker is unavailable

Run the profile-specific checks and repair only Docker:

```bash
dot doctor --profile kubuntu-laptop
dot apply --profile kubuntu-laptop --tags docker
```

After the first apply, log out and back in so the new `docker` group membership
reaches the desktop session. Membership in this group grants root-equivalent
control through the Docker daemon; it is intentional for this personal
workstation profile.

In WSL, dotfiles owns a native engine rather than Docker Desktop integration.
If preflight says systemd is unavailable, update WSL, enable systemd in
`/etc/wsl.conf`, and run `wsl --shutdown` from PowerShell. If it detects the
Docker Desktop proxy, disable that distribution under Docker Desktop's WSL
Integration settings, shut WSL down, and retry. Do not keep both engines active.

## Tailscale is installed but offline

Check the managed package, daemon, and enrollment independently:

```bash
dot doctor --profile kubuntu-laptop
systemctl status tailscaled
tailscale status
```

Repair the package and service with
`dot apply --profile kubuntu-laptop --tags tailscale`. A new installation
reports `NeedsLogin` until you run `sudo tailscale up` and authenticate with the
browser URL it prints. Dotfiles intentionally stores neither an auth key nor
Tailscale's machine identity.

On Windows, install the recorded `Tailscale.Tailscale` package through Winget
and sign in using the native application. Do not also run Tailscale inside WSL;
the WSL profiles intentionally omit it and rely on the Windows host network.

## Neovim does not start cleanly

Test the managed configuration without opening the UI:

```bash
dot nvim status --profile kubuntu-laptop
dot doctor --profile kubuntu-laptop
```

The first command loads the locked plugin graph, required modules, mappings,
clipboard option, and Lua Tree-sitter parser in headless mode. Repair the
managed link with `dot apply --profile kubuntu-laptop --tags nvim`. On WSL,
substitute the personal or work profile.

If a plugin update is available, use `dot nvim update --check` before applying
it. Do not run `:Lazy update` as the normal maintenance path: the dot command
tests the candidate away from live editor data and records a rollback ID. If a
promoted release regresses at runtime, use the printed
`dot nvim rollback RUN_ID --profile PROFILE` command.

Language servers and formatters live under Neovim's Mason data directory. Open
`:Mason` to inspect an individual installation and `:LspInfo` to inspect the
current buffer. Kubuntu's native clipboard needs `wl-copy`, while WSL uses
`clip.exe` and PowerShell through its explicit clipboard provider.

## Codex Remote Control is unavailable

Check the managed user service:

```bash
systemctl --user status codex-remote-control.service
codex app-server daemon version
loginctl show-user "$USER" --property=Linger
```

If the standalone CLI or native daemon state is missing, rerun
`dot apply --profile kubuntu-laptop --tags codex`. The profile installs the
verified stable standalone release, removes the obsolete parallel app-server
units, and bootstraps Codex's native daemon with Remote Control enabled.

Check the native state with:

```bash
codex app-server daemon version
cat ~/.codex/app-server-daemon/settings.json
```

If Desktop reports that it could not enable Remote Control while the logs say
`409 Remote app server already online`, a legacy raw app-server is competing
with Desktop. Fully close active Codex work, then run:

```bash
dot apply --profile kubuntu-laptop --tags codex
```

The apply intentionally disconnects the obsolete owner once, writes the native
daemon preference, and restores the background connection. Reopen Desktop only
after the apply completes.
