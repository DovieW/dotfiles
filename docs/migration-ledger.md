# Migration ledger

Decisions use the most recent substantive commit in `files`, not file
timestamps alone. “Retain” means the material stays private in `files`; “move”
means its reusable configuration now has an authoritative replacement here.

| Source | Latest substantive activity | Decision | Destination or reason |
|---|---:|---|---|
| `other/linux_setup/shell` | 2026-06-11 | Move | `config/shell`; Zsh, full Bash, and `mbash` |
| `other/linux_setup/tmux` | 2025-12-16 | Move and clean | `config/tmux`; TPM and plugins are provisioned from upstream |
| `programs/git` | 2026-04-20 | Move | `config/git`; stale B&H/Kalman variants retired |
| `programs/powershell` | 2026-01-15 | Move | `config/powershell` |
| `programs/docker` | 2026-07-15 | Move and replace | `config/docker` helpers; one-off WSL updater replaced by the native Docker Ansible role |
| `programs/autohotkey` | 2026-05-20 | Move active v2 | `config/autohotkey`; private hotstrings excluded |
| `programs/flameshot` | 2026-04-21 | Move | `config/flameshot` |
| `programs/alacritty` | 2024-10-30 | Move and repair | `config/alacritty` |
| `programs/lazygit`, `programs/lazydocker` | 2024-03 | Move config | `config/lazygit`, `config/lazydocker` |
| `programs/mpv` | 2024-11-17 | Move config only | `config/mpv`; third-party scripts stay private |
| `programs/windows_terminal` | 2024-05-26 | Move | `config/windows-terminal` |
| `programs/Regedits` | 2025-09-21 | Move selected | Active sanitized registry customizations |
| `programs/ssh` | 2025-03-01 | Replace | Sanitized template only; no private key imported |
| `programs/ansible` | 2025-08-07 | Retire | Placeholder replaced by `ansible/` |
| `programs/komorebi` | 2024-12-23 | Retire | Superseded Windows UI setup |
| `other/linux_setup/{i3,sway}` and X11/GNOME/Pop setup | 2024 | Retire | Superseded by KDE/Wayland profile |
| `programs/terminus` | 2026-07-28 | Retain | Independent project |
| `programs/ynab` | 2026-01-21 | Retain | Independent private service tool |
| `programs/controld`, `programs/nextdns` | 2026-01-18 | Retain | Private service state and credentials |
| `programs/chatgpt` | 2026-02-06 | Retain | Independent reporting project |
| `programs/copilot-cli` | 2026-01-15 | Retain | Experimental project material |
| `programs/truenas-scale`, `TrueNAS Core`, `meshcentral` | 2026-01/2023 | Retain | Infrastructure tooling and backups |
| `programs/Bruno`, `Insomnia` | 2026-04/2023 | Retain | API-client state |
| `programs/OBS`, `EventGhost`, `LGHUB`, `MPC-BE` | 2023 | Retain | Application exports/backups |
| `programs/qBittorrent` | 2026-06-15 | Retain | Third-party search plugins and app state |
| `programs/qmk` | 2025-05-01 | Retain | Keyboard firmware project |
| `programs/powertoys`, `windhawk` | 2025 | Retain | Binary application backups |
| `programs/scrcpy`, `Newpipe` | 2025/2023 | Retain | Device tooling/data |
| `programs/remmina`, `other/linux_setup/remmina` | 2024 | Migrate sanitized flow | Stock Remmina preferences and ephemeral F5 profile generation live in dotfiles; private targets and tokens remain runtime-only |
| `programs/lazygit`, `programs/lazydocker` setup scripts | 2024 | Retire setup | Replaced by profile-driven application |
| `DovieW/nvim-config` | 2024-08-14 | Replace, retain history | `config/nvim`; original repository remains unchanged and is no longer deployed |

The existing secret history in `files` is intentionally not rewritten by this
migration. Superseded private-key material may disappear from its current
branch as part of later source cleanup, but remains in Git history unless the
owner starts a separate remediation project.
