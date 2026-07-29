# Dovie's dotfiles

Reproducible configuration for Kubuntu, personal and work WSL, Windows, and
Termux. The repository is public by design: secrets, private repository lists,
SSH private keys, proprietary fonts, and machine state belong in Bitwarden or
local state, never here.

## Quick start

```bash
git clone https://github.com/DovieW/dotfiles ~/repos/dotfiles
~/repos/dotfiles/bin/dot bootstrap --profile kubuntu-laptop
```

Available profiles are `kubuntu-laptop`, `wsl-personal`, `wsl-work`,
`windows-host`, and `termux`.

The bootstrap command checks prerequisites before changing anything. Windows
bootstrap is inventory-only and never installs prerequisites or applications.

## Daily commands

```text
dot apply --profile kubuntu-laptop
dot doctor --profile kubuntu-laptop
dot package add ripgrep --profile common-linux
dot repos sync --profile kubuntu-laptop
dot capture kde
dot diff kde
dot rollback RUN_ID
```

See [Architecture](docs/architecture.md), [Maintenance](docs/maintenance.md),
and [Troubleshooting](docs/troubleshooting.md).
