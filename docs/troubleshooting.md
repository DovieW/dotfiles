# Troubleshooting

## Bitwarden is unavailable

Run `bw status`. If it reports unauthenticated, run `bw login` once. Do not add
`BW_SESSION` to `.bashrc`, `.zshrc`, an env file, or this repository.

## GitHub registration is pending

Install GitHub CLI, run `gh auth login`, and rerun:

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

Log out and back in after restoring panel or shortcut configuration. Portable
setup intentionally does not run `kscreen-doctor` or replace KScreen state.

## Shell startup is slow

Profile Zsh with:

```bash
PROFILE_ZSH_STARTUP=1 zsh -i -c exit
```

Use `mbash` for an intentionally minimal shell and `fullbash` to switch back to
the complete Bash profile.
