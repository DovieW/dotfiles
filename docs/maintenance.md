# Maintenance

## Add a package

```bash
dot package add ripgrep --profile common-linux
dot package add libssl-dev --profile wsl-personal --provider apt
```

The command edits the manifest and applies the package role on Linux. It never
commits. On Windows, specify `winget`, `scoop`, or `psgallery`; the package is
recorded but not installed.

External Debian applications declare their official GitHub source and asset
pattern in `packages/external-deb.yml`. Apply resolves the newest non-draft,
non-prerelease asset and verifies GitHub's published SHA-256 digest before
installation.

## Version policy

Machine-level programs follow the latest stable release offered by their
declared provider. Version numbers and mutable installer checksums are not
committed merely to freeze a workstation:

- APT, Homebrew, Snap, and Termux packages advance to current stable repository
  candidates during a package apply.
- Bitwarden Desktop and Obsidian resolve their latest matching stable GitHub
  release dynamically.
- Codex and Vite+ use their official stable channels and supported updaters.
- Windows remains inventory-only, so dotfiles reports rather than changes its
  application versions.

Project lockfiles, `.node-version`, language runtime constraints, and explicit
compatibility bounds are still valid pins. Those make a project repeatable;
they do not freeze the general-purpose workstation.

Update every program managed by a profile with:

```bash
dot update --profile kubuntu-laptop
```

The same action is available as **Update managed programs** in the fzf command
palette. It updates repository-backed packages first, then invokes supported
stable-channel updaters for Codex and Vite+.

Docker Engine, Compose, and Buildx advance through Docker's official stable APT
repository during the same update. To apply or repair only Docker:

```bash
dot apply --profile kubuntu-laptop --tags docker
```

Use the matching WSL profile name inside WSL. The Docker role is idempotent and
does not remove `/var/lib/docker`, images, containers, volumes, or `/etc/docker`.

Tmux uses `~/.config/tmux/tmux.conf`, linked to the authoritative repository
copy. TPM and configured plugins are installed and updated from their upstream
default branches by `dot apply` and `dot update`. Apply only this subsystem with:

```bash
dot apply --profile kubuntu-laptop --tags packages,tmux
```

## Update captured configuration

Edit portable files in this repository directly. For a reviewed KDE change:

```bash
dot capture kde
git diff -- config/kde
./scripts/check-public-safety
dot apply --profile kubuntu-laptop
```

Never capture the complete `.config` directory.

For routine changes, open the fzf command palette:

```bash
dot
```

Choose **Save configuration changes**. The next fzf view lists only drifted
managed files, supports multi-selection, and shows a live Delta preview.
Choose **Save, validate, commit, and push** to finish the complete workflow.
Unrelated unstaged repository work is preserved, while an already-dirty
selected file or a non-empty Git index is rejected.

`dot save` jumps directly to the selector. `dot save spectacle` restricts it
to Spectacle preferences and keyboard shortcuts.

To capture only reviewed files, repeat `--only` with allowlisted basenames:

```bash
dot capture kde --only spectaclerc --only kglobalshortcutsrc
```

`dot apply` records the last deployed KDE hashes. If a managed live file has
changed since that deployment, apply stops instead of overwriting it. Review
with `dot diff kde` and capture the intended file. `--force-kde` is reserved
for an intentional repository-to-machine replacement; backups are still made.
In an interactive terminal, `dot diff kde` uses Delta as its pager; redirected
output remains a standard unified diff suitable for logs and automation.

## Rotate a device key

Remove the named device item from Bitwarden and revoke its authentication and
signing entries from GitHub. Then run:

```bash
dot secrets sync --profile kubuntu-laptop
```

This creates and registers a new Ed25519 key. WSL and Termux should rerun the
same command to refresh their local permission-locked key.

## Validate

```bash
./tests/run
dot apply --profile kubuntu-laptop
dot apply --profile kubuntu-laptop
dot doctor --profile kubuntu-laptop
./scripts/check-public-safety
```

The second apply must report zero configuration changes.

## Codex Remote Control

The Kubuntu profile manages `codex-remote-control.service` as a systemd user
service. Inspect it with:

```bash
systemctl --user status codex-remote-control.service
journalctl --user -u codex-remote-control.service
```

The service starts during boot and systemd restarts it after a failure. The
profile enables user lingering so it also remains available after logout. It
uses the standalone Codex installation at `~/.local/bin/codex`; an npm-managed
Codex installation does not satisfy this requirement.

The official installer and stable-channel policy are stored in
`packages/codex.yml`. A normal apply installs Codex only when the managed
standalone installation is absent. Any healthy managed stable version is
accepted.

To update Codex:

```bash
dot codex update
```

The update leaves an already-running Remote Control process alone because
restarting it disconnects active remote sessions. The new release takes effect
after the next service restart or reboot.

## Vite+

Vite+ follows the official stable channel declared in
`packages/vite-plus.yml`. Normal apply installs it when missing, and native
upgrades do not create configuration drift. Either command is valid:

```bash
vp upgrade
dot vite-plus update
```

`dot vite-plus update` delegates to Vite+'s stable updater when Vite+ is already
managed. The installer runs with `VP_NODE_MANAGER=no`; dotfiles owns shell
startup. `vp env setup --env-only` generates the machine-local wrapper and
completion integration without rewriting `.bashrc` or `.zshrc`.
