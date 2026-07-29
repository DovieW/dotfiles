# Maintenance

## Add a package

```bash
dot package add ripgrep --profile common-linux
dot package add libssl-dev --profile wsl-personal --provider apt
```

The command edits the manifest and applies the package role on Linux. It never
commits. On Windows, specify `winget`, `scoop`, or `psgallery`; the package is
recorded but not installed.

External Debian applications are pinned in `packages/external-deb.yml` with an
upstream release URL and SHA-256 digest. Update all three values together,
review the upstream release, and run `scripts/fetch-external-deb NAME` before
applying.

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

The pinned release, official installer URL, and reviewed installer SHA-256 are
stored in `packages/codex.yml`. A normal apply installs Codex only when the
managed standalone installation is absent. If the installed version differs
from the pin, apply stops instead of silently upgrading or downgrading it.

To update Codex:

1. Download and review the current official installer.
2. Update `release` and `installer_sha256` in `packages/codex.yml`.
3. Run `dot codex update`.
4. Review the diff, run the validation suite, and commit the manifest update.

The update leaves an already-running Remote Control process alone because
restarting it disconnects active remote sessions. The new release takes effect
after the next service restart or reboot.

## Vite+

Vite+ is pinned in `packages/vite-plus.yml`. Normal apply installs a missing
release but refuses an implicit version change. To upgrade:

1. Review the current official installer.
2. Update `release` and `installer_sha256` in `packages/vite-plus.yml`.
3. Run `dot vite-plus update`.
4. Open fresh Bash and Zsh sessions and run `vp env doctor`.
5. Run the validation suite and commit the manifest update.

The installer runs with `VP_NODE_MANAGER=no`; dotfiles owns shell startup.
`vp env setup --env-only` generates the machine-local wrapper and completion
integration without rewriting `.bashrc` or `.zshrc`.
