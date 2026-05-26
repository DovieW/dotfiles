# Dovie's dotfiles

Public Windows + WSL dotfiles managed with [chezmoi](https://www.chezmoi.io/).

This repo is intentionally small: it configures the shell/user environment. Personal scripts, generated files, credentials, homelab config, and experiments stay in the private `files` repo or in Bitwarden.

## New machine

See [`NEW_MACHINE.md`](NEW_MACHINE.md) for the full Windows + WSL setup flow.

Short version:

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
winget install --id twpayne.chezmoi -e
chezmoi init DovieW/dotfiles
pwsh -NoProfile -ExecutionPolicy Bypass -File "$(chezmoi source-path)\scripts\setup.ps1"
```

For WSL:

```sh
sudo apt update
sudo apt install -y git curl
sh -c "$(curl -fsLS get.chezmoi.io)"
~/.local/bin/chezmoi init DovieW/dotfiles
"$(~/.local/bin/chezmoi source-path)/scripts/setup-wsl.sh"
```

## Secrets

Secrets live in Bitwarden, not in this repo. Setup modules that require secrets are marked before they run and can help install/login/unlock the Bitwarden CLI.
