# Maintenance

## Add a package

```bash
dot package add ripgrep --profile common-linux
dot package add libssl-dev --profile wsl-personal --provider apt
```

The command edits the manifest and applies the package role on Linux. It never
commits. On Windows, specify `winget`, `scoop`, or `psgallery`; the package is
recorded but not installed.

External Debian applications declare their official GitHub source and asset
pattern in `packages/external-deb.yml`. Apply resolves the newest non-draft,
non-prerelease asset and verifies GitHub's published SHA-256 digest before
installation.

## Version policy

Machine-level programs follow the latest stable release offered by their
declared provider. Version numbers and mutable installer checksums are not
committed merely to freeze a workstation:

- A package apply installs and reconciles the packages declared by the selected
  profile.
- Bitwarden Desktop and Obsidian resolve their latest matching stable GitHub
  release dynamically.
- ChatGPT Desktop with Codex follows OpenAI's signed stable APT repository.
- Codex and Vite+ use their official stable channels and supported updaters.
- `git-sync` follows its maintained upstream `master` branch because the
  project does not publish releases; dotfiles records the installed revision
  and replaces it only after downloading and syntax-checking the new script.
- Windows remains inventory-only, so dotfiles reports rather than changes its
  application versions.

Project lockfiles, `.node-version`, language runtime constraints, and explicit
compatibility bounds are still valid pins. Those make a project repeatable;
they do not freeze the general-purpose workstation.

Update every installed system package and application supported by the profile:

```bash
dot update --profile kubuntu-laptop
dot update --profile kubuntu-laptop --check
dot update --profile kubuntu-laptop --system
dot update --profile kubuntu-laptop --apps
```

On Kubuntu, the shorter `dot update` form infers the `kubuntu-laptop` profile.
WSL requires an explicit personal or work profile because both are valid there.

The same scopes are available under **Update** in the fzf command palette.
**Update everything** updates all installed APT packages, all Snaps, all
Homebrew formulae, managed external Debian applications, Tmux plugins, Codex,
Vite+, git-sync, InputActions, Neovim plugins, and curated Mason language tools. A
package-manager transaction already in progress causes an actionable refusal
instead of competing for native locks.

## Automatic repository sync

`g sync` is `git sync`: Git discovers the managed `git-sync` executable on
`PATH`, commits ordinary local changes, fetches, integrates a safe
non-divergent upstream update, and pushes. The primary `master` and `main`
branches opt in by default and include new files, preserving the historical
workflow. Other branches refuse automatic mutation unless the repository opts
in explicitly or `git sync -s` is used. Install, repair, or update only this
utility with:

```bash
dot apply --profile kubuntu-laptop --tags git
```

Because sync creates a normal signed commit, the Bitwarden SSH agent must be
available whenever the repository's signing policy requires it. Conflicts,
detached HEADs, and other non-routine states are rejected for manual review.

## Interactive command palette

Run `dot` anywhere to open the main interface. Each FZF row has an action name
on the left and a plain-language description on the right. Type to filter,
press Enter to open or run an item, and press Escape to return one level. The
active profile appears in the prompt and can be switched from the main menu.

The palette exposes the complete routine interface:

- updates, from the whole machine down to one provider or tool;
- full and tagged apply or repair operations;
- KDE save, selective capture, drift review, apply, and rollback;
- Neovim tests, plugin checks and updates, Mason tools, repair, and rollback;
- repository sync, package manifests, Tailscale, Docker, Codex, Vite+, and
  gestures;
- doctor, validation, failed-service, and Git diagnostics;
- device identity, bootstrap, Bitwarden secret provisioning, and repository
  restoration.

The explicit command-line forms remain available for scripts and remote work.

### Neovim plugins

Normal application updates include Neovim plugins:

```bash
dot nvim status --profile kubuntu-laptop
dot nvim update --profile kubuntu-laptop --check
dot nvim update --profile kubuntu-laptop
dot nvim tools --profile kubuntu-laptop
```

The update never experiments in the live editor. It copies the configuration
and lockfile into isolated XDG directories, updates that candidate, checks Lua
formatting, and runs the headless smoke test. Only a passing candidate replaces
the repository lockfile. The live plugins are then restored to that exact lock,
the complete dotfiles validation suite runs, and a personal profile creates a
signed lockfile-only commit and pushes it.

The command refuses to publish if the dotfiles worktree is dirty or its branch
is not synchronized with upstream. A work WSL profile consumes the committed
lock but never publishes plugin changes. Every promoted update prints a
rollback ID:

```bash
dot nvim rollback RUN_ID --profile kubuntu-laptop
```

`dot nvim tools` upgrades the curated Mason-managed language servers,
formatters, and linters, then runs the same headless smoke test. Rollback
restores the previous lock, reconciles and retests the live plugins,
then commits and pushes the result. Plugin source and Mason packages remain
machine-local under Neovim's standard data directory.

To change the editor configuration itself, edit `config/nvim`, run
`dot nvim status`, and commit the reviewed configuration normally. Apply only
the managed link with:

```bash
dot apply --profile kubuntu-laptop --tags nvim
```

Docker Engine, Compose, and Buildx advance through Docker's official stable APT
repository during the same update. To apply or repair only Docker:

```bash
dot apply --profile kubuntu-laptop --tags docker
```

Use the matching WSL profile name inside WSL. The Docker role is idempotent and
does not remove `/var/lib/docker`, images, containers, volumes, or `/etc/docker`.

Tailscale advances through its official stable APT repository during normal
Kubuntu applies and updates. Install or repair only that subsystem with:

```bash
dot apply --profile kubuntu-laptop --tags tailscale
```

The first apply enables `tailscaled` but deliberately stops short of joining a
tailnet. Enroll this physical machine once with `sudo tailscale up`; later
applies preserve its local node identity. Do not run the Linux client inside
either WSL profile when the Windows host client is active.

Tmux uses `~/.config/tmux/tmux.conf`, linked to the authoritative repository
copy. TPM and configured plugins are installed and updated from their upstream
default branches by `dot apply` and `dot update`. Apply only this subsystem with:

```bash
dot apply --profile kubuntu-laptop --tags packages,tmux
```

Tmux owns mouse reporting inside Ghostty. Its managed root-table binding opens
the OSC 8 hyperlink or validated URL under Ctrl+left-click, replacing tmux's
default marked-pane swap action.

Ghostty uses `~/.config/ghostty/config`, copied from the authoritative
repository configuration. It deliberately provides no window chrome, tabs, or
scrollbar because tmux owns those functions. FiraCode Nerd Font Mono is resolved
from Nerd Fonts' latest stable GitHub release and checked against the release's
published SHA-256 manifest. Apply Ghostty, the font, and its configuration with:

```bash
dot apply --profile kubuntu-laptop --tags packages
```

## Customize touchpad gestures

The portable gesture map is
`config/inputactions/config.yaml`. It reloads automatically when changed; use
the explicit command when testing or diagnosing it:

```bash
dot gestures reload
dot gestures status
```

`dot gestures reload` installs the tracked gesture file and its helper before
reloading InputActions, so it is the quick no-sudo path after editing the
repository. Three-finger vertical volume control is continuous: distance and
speed determine the size of the adjustment, and reversing during a swipe
reverses the volume change.

`dot update --profile kubuntu-laptop` follows the newest stable InputActions
releases and rebuilds its KWin plugin after a KWin package change. A newly
rebuilt plugin may require logging out and back in before the running
compositor can use the new binary.

The separate CIRQ touchpad jump workaround is a temporary system-level libinput
override. Apply or verify it with:

```bash
dot apply --profile kubuntu-laptop --tags touchpad
dot doctor --profile kubuntu-laptop
```

Review upstream libinput issue #1297 after libinput upgrades and retire the
override once Ubuntu contains the arrival-time fix.

The interactive `dot` palette also contains a gesture-management submenu.
InputActions intentionally retains its upstream emergency chord: hold
Backspace, Space, and Enter together for two seconds to suspend gesture
handling until the next configuration reload.

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

Choose **Save and configuration → Save changed settings**. The next fzf view lists only drifted
managed files, supports multi-selection, and shows a live Delta preview.
Choose **Save, validate, commit, and push** to finish the complete workflow.
Unrelated unstaged repository work is preserved, while an already-dirty
selected file or a non-empty Git index is rejected.

`dot save` jumps directly to the selector. `dot save spectacle` restricts it
to Spectacle preferences and keyboard shortcuts.

`dot save panel` restricts the selector to panel-adjacent KDE appearance,
KRunner, shortcuts, and the GitHub Dark appearance files. Taskbar structure and
geometry are managed by the panel-profile manifest and `dot panel`; generated
Plasma containment IDs remain host-local. Panel deployment is transactional:
dotfiles creates one backup run, applies the selected profile through Plasma's
supported live scripting API, and validates the result without restarting the
desktop shell. The successful apply prints its recovery run ID.

Panel profiles are separate from capturing panel preferences:

```bash
dot panel
dot panel list
dot panel status
dot panel save
dot panel use centered-compact
```

The complete FZF workflow is available under **Save and configuration →
Taskbar and System Tray**: validate the live taskbar, switch profiles, save the
pinned order and tray visibility choices, reapply the selected profile, or list
every profile.
Taskbar status is also available under **Diagnostics**, and profile repair is
available under **Apply and repair**. Switching writes only host-local selection
state and applies the declarative manifest through Plasma's live API. Plasma's
generated containment IDs and geometry remain host-local; taskbar structure
belongs to the manifest rather than a captured machine-specific applet file.

After experimenting in Plasma's panel editor, run `dot panel status`. A matching
result means the selected profile already describes the live taskbar. A drift
result means the intended structure must be incorporated into
`config/kde/panel-profiles.json` or the shared panel builder before it is
portable; do not capture Plasma's generated containment IDs as configuration.
Pinned-app order and System Tray visibility are the editable preferences: drag
the taskbar icons or choose which tray entries are always visible, automatic,
or always hidden, then run `dot panel save`. That command captures both live
preferences, validates the complete repository, and commits and pushes only
the panel manifest.

Running tasks are filtered to the current virtual desktop. Applications belong
to every taskbar only through an explicit KWin all-desktops rule; Ghostty is the
only normal application managed that way.

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

## Maintain the lock screen

The managed lock screen is separate from SDDM and can be previewed without
locking the session:

```bash
dot lockscreen preview
```

Apply only its shell package, private wallpaper, and two KDE configuration
files with:

```bash
dot apply --profile kubuntu-laptop --tags lockscreen
```

If a Plasma update makes the custom QML unusable, KScreenLocker falls back to
its compiled emergency UI. To deliberately return future locks to the complete
stock Plasma shell, run `dot lockscreen stock`; the command backs up
`plasmashellrc`, and the managed theme remains available for a later apply.
All three actions are also reachable under **Save and configuration** in the
fzf palette.

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
dot nvim status --profile kubuntu-laptop
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

The official installer and stable-channel policy are stored in
`packages/codex.yml`. A normal apply installs Codex only when the managed
standalone installation is absent. Any healthy managed stable version is
accepted.

To update Codex:

```bash
dot codex update
```

The update leaves an already-running Remote Control process alone because
restarting it disconnects active remote sessions. The new release takes effect
after the next service restart or reboot.

## Vite+

Vite+ follows the official stable channel declared in
`packages/vite-plus.yml`. Normal apply installs it when missing, and native
upgrades do not create configuration drift. Either command is valid:

```bash
vp upgrade
dot vite-plus update
```

`dot vite-plus update` delegates to Vite+'s stable updater when Vite+ is already
managed. The installer runs with `VP_NODE_MANAGER=no`; dotfiles owns shell
startup. `vp env setup --env-only` generates the machine-local wrapper and
completion integration without rewriting `.bashrc` or `.zshrc`.
