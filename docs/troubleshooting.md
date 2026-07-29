# Troubleshooting

## Bitwarden is unavailable

Run `bw status`. If it reports unauthenticated, run `bw login` once. Do not add
`BW_SESSION` to `.bashrc`, `.zshrc`, an env file, or this repository.

If this is the first machine and the bootstrap Secure Note does not exist, run:

```bash
dot secrets initialize --draft ~/.config/dotfiles/bootstrap-draft.json
```

Initialization refuses to overwrite an existing note.

## GitHub registration is pending

Install GitHub CLI, authorize both SSH key-management scopes, and rerun:

```bash
gh auth login -h github.com -p ssh -w \
  -s admin:public_key,admin:ssh_signing_key
```

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

### KDE apply refuses local drift

This means an allowlisted KDE file changed through System Settings or an
application after its last deployment. Review it before choosing a direction:

```bash
dot diff kde
dot capture kde --only NAME
```

Use `dot apply --profile kubuntu-laptop --force-kde` only when the committed
repository copy should intentionally replace the live file. The replaced file
is backed up for rollback.

Log out and back in after restoring panel or shortcut configuration. Portable
setup intentionally does not run `kscreen-doctor` or replace KScreen state.

## Shell startup is slow

Profile Zsh with:

```bash
PROFILE_ZSH_STARTUP=1 zsh -i -c exit
```

## Vite+ is missing or `vp env use` does not persist

Run:

```bash
scripts/install-vite-plus --check
vp env setup --env-only
```

Then open a new shell and run `vp env doctor`. Do not manually add Vite+
installer lines to `.bashrc` or `.zshrc`; dotfiles sources the generated
`$VP_HOME/env` file after shell completion initialization.

Use `mbash` for an intentionally minimal shell and `fullbash` to switch back to
the complete Bash profile.

## Package updates fail before the first APT task

Interactive `dot apply` and `dot update` runs preflight sudo authorization
before Ansible starts. They reuse a valid sudo timestamp or prompt once with
`sudo -v`. Noninteractive runs cannot request a password and instead stop with
an instruction to authorize sudo in a terminal before retrying. No package
task runs when this preflight fails.

## Codex Remote Control is unavailable

Check the managed user service:

```bash
systemctl --user status codex-remote-control.service
journalctl --user -u codex-remote-control.service --since today
loginctl show-user "$USER" --property=Linger
```

If the standalone CLI is missing, rerun
`dot apply --profile kubuntu-laptop`; the profile installs the latest stable
release through the official installer, whose release archive verification is
retained. Do not run `codex app-server daemon bootstrap` from a session
currently connected through that daemon: bootstrapping replaces the app-server
and disconnects the session.
