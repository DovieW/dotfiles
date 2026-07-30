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

Bootstrap links the canonical CLI to `~/.local/bin/dot`; afterward, use the
short `dot` command shown throughout this documentation.

Available profiles are `kubuntu-laptop`, `wsl-personal`, `wsl-work`,
`windows-host`, and `termux`.

The bootstrap command checks prerequisites before changing anything. Windows
bootstrap is inventory-only and never installs prerequisites or applications.
When secrets are enabled, bootstrap runs GitHub's browser authorization before
unlocking Bitwarden and requests both authentication-key and signing-key
management scopes.

On the Kubuntu profile, the standalone Codex CLI is expected at
`~/.local/bin/codex`. Applying the profile installs the latest stable standalone
release when it is missing, then enables a supervised user service that keeps
Codex Remote Control running across logins and restarts it after a failure.
User lingering keeps the service available after logout and starts it during
boot without waiting for an interactive login.

For a new vault, create the private bootstrap note once from a permission-locked
local draft:

```bash
dot secrets initialize --draft ~/.config/dotfiles/bootstrap-draft.json
```

The command refuses to overwrite an existing `dotfiles/bootstrap-v1` item.

## Daily commands

```text
dot apply --profile kubuntu-laptop
dot update --profile kubuntu-laptop
dot nvim status --profile kubuntu-laptop
dot nvim update --profile kubuntu-laptop
dot doctor --profile kubuntu-laptop
dot package add ripgrep --profile common-linux
dot repos sync --profile kubuntu-laptop
dot capture kde
dot diff kde
dot rollback RUN_ID
```

Run `dot` with no arguments for the fzf command palette. Its save workflow
shows only changed managed files, provides a Delta preview, supports
multi-selection, validates, creates a signed commit, and pushes:

```bash
dot
```

`dot save` opens that workflow directly. `dot save spectacle` limits the
selector to Spectacle preferences and keyboard shortcuts.

Choose **Update system and applications** in the palette, or run `dot update`,
to coordinate all installed APT, Snap, Homebrew, external-Debian, Codex,
Vite+, and tested Neovim plugin updates through their native stable providers.
Use `--system` or `--apps`
for one category and `--check` for a read-only report. `dot apply` remains the
separate operation that reconciles the declared package manifest.
On this Kubuntu laptop, `dot update` infers `kubuntu-laptop`; `--profile` remains
available as an override and is required only where multiple profiles apply,
such as personal versus work WSL.

Vite+ is a first-class tool on Kubuntu and WSL and follows its stable channel.
New Bash and Zsh
sessions load its generated environment so `vp env use` can update the current
shell without allowing the upstream installer to rewrite managed rc files.

Kubuntu and both WSL profiles own a native Docker Engine, Docker Compose, and
Buildx installation from Docker's official stable Ubuntu repository. WSL does
not use Docker Desktop integration. See [Docker](docs/docker.md) before first
applying a WSL profile.

Kubuntu installs Tailscale from its official stable APT repository and enables
the daemon. Tailnet enrollment remains an explicit browser-authenticated step.
Windows records the native Tailscale client; WSL deliberately relies on that
host client instead of nesting another VPN. See [Tailscale](docs/tailscale.md).

See [Architecture](docs/architecture.md), [Maintenance](docs/maintenance.md),
[Docker](docs/docker.md), [Tailscale](docs/tailscale.md), and
[Troubleshooting](docs/troubleshooting.md).
