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
