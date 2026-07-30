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
setup intentionally does not run `kscreen-doctor` or replace KScreen state.

## Closing the lid suspends the laptop

The managed policy ignores lid closure and disables automatic suspend for AC,
battery, and low-battery profiles. It preserves manual Sleep and the physical
power button. Apply both the live PowerDevil policy and the system fallback:

```bash
dot apply --profile kubuntu-laptop --tags kde
```

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
is not sufficient after correcting the session agent.

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

## Codex Remote Control is unavailable

Check the managed user service:

```bash
systemctl --user status codex-remote-control.service
journalctl --user -u codex-remote-control.service --since today
loginctl show-user "$USER" --property=Linger
```

If the standalone CLI is missing, rerun
`dot apply --profile kubuntu-laptop`; the profile installs the latest stable
release through the official installer, whose release archive verification is
retained. Do not run `codex app-server daemon bootstrap` from a session
currently connected through that daemon: bootstrapping replaces the app-server
and disconnects the session.
