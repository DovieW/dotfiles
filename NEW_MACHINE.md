# New machine setup

The setup goal is one clear flow for Windows-first machines with WSL.

## 1. Windows host

Open PowerShell 7 as your normal user.

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
winget install --id twpayne.chezmoi -e
chezmoi init DovieW/dotfiles
pwsh -NoProfile -ExecutionPolicy Bypass -File "$(chezmoi source-path)\scripts\setup.ps1"
```

The setup script is interactive by default. It also supports profiles:

```powershell
pwsh -File "$(chezmoi source-path)\scripts\setup.ps1" -WindowsCore
pwsh -File "$(chezmoi source-path)\scripts\setup.ps1" -DotfilesOnly
pwsh -File "$(chezmoi source-path)\scripts\setup.ps1" -AllSafe
pwsh -File "$(chezmoi source-path)\scripts\setup.ps1" -WithBitwarden
pwsh -File "$(chezmoi source-path)\scripts\setup.ps1" -DryRun
```

Modules that need secrets will ask before using Bitwarden. If Bitwarden CLI is missing, setup can install it with winget.

## 2. Bitwarden

When a selected module needs secrets:

```powershell
pwsh -File "$(chezmoi source-path)\scripts\unlock-bitwarden.ps1"
```

This logs in if needed, unlocks the vault, and sets `BW_SESSION` for that PowerShell session. Do not write `BW_SESSION` to a profile file.

## 3. WSL

Install your WSL distro, then run:

```sh
sudo apt update
sudo apt install -y git curl
sh -c "$(curl -fsLS get.chezmoi.io)"
~/.local/bin/chezmoi init DovieW/dotfiles
"$(~/.local/bin/chezmoi source-path)/scripts/setup-wsl.sh"
```

Profiles:

```sh
"$(chezmoi source-path)/scripts/setup-wsl.sh" --wsl-core
"$(chezmoi source-path)/scripts/setup-wsl.sh" --dotfiles-only
"$(chezmoi source-path)/scripts/setup-wsl.sh" --all-safe
"$(chezmoi source-path)/scripts/setup-wsl.sh" --with-bitwarden
"$(chezmoi source-path)/scripts/setup-wsl.sh" --dry-run
```

## 4. Private repos

After public dotfiles work, clone private repos only on machines that need them. The old `DovieW/files` repo remains the private workbench/archive.
