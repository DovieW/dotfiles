# Maintenance

## Add a package

```bash
dot package add ripgrep --profile common-linux
dot package add libssl-dev --profile wsl-personal --provider apt
```

The command edits the manifest and applies the package role on Linux. It never
commits. On Windows, specify `winget`, `scoop`, or `psgallery`; the package is
recorded but not installed.

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
