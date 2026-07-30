# Architecture

## Repository boundary

This repository contains portable configuration, setup logic, schemas, and
documentation. The private `files` repository continues to contain projects,
exports, backups, third-party bundles, and private service state.

Secrets and the full repository clone manifest live in Bitwarden. Generated
identity files live under `~/.config/dotfiles` with mode `0600`. Runtime state
and rollback data live under `~/.local/state/dotfiles`.

## Profiles

Profiles are JSON-formatted YAML documents so the bootstrap can parse them with
Python's standard library before Ansible is available. A profile inherits zero
or more parents, enables features, selects a personal or work identity, and
adds provider-specific packages.

Linux package ownership is intentional:

- APT owns system libraries, desktop integration, KDE, and the login shell.
- Homebrew owns modern cross-distribution CLI tools.
- Official GitHub stable releases own Bitwarden Desktop and Obsidian; their
  release-provided SHA-256 digests are verified dynamically.
- The official stable channel owns the standalone Codex CLI release.
- The official stable channel owns Vite+ on Kubuntu and WSL.
- Docker's official stable Ubuntu APT repository owns native Docker Engine,
  Compose, and Buildx on Kubuntu and WSL.
- Tailscale's official stable Ubuntu APT repository owns the native Kubuntu
  client. The Windows client is inventory-only, and WSL uses the Windows host
  rather than running a nested Tailscale node.
- Snap is exception-only and no application is currently managed through it.
- Termux uses `pkg`.
- Windows manifests are records and never trigger application installation.

Program manifests declare ownership, source, and release channel rather than
freezing workstation versions. Apply upgrades managed APT, Homebrew, external
Debian, Snap, and Termux packages to the latest stable releases their providers
offer. Native supported updaters such as `vp upgrade` are valid and do not
create dotfiles drift. Project dependency lockfiles and project runtime pins
remain authoritative inside each project.

## Terminal

Ghostty is the preferred native Kubuntu terminal and is installed from
Ubuntu's current stable repository candidate. Its managed configuration removes
window decorations, the tab bar, and the scrollbar, starts maximized, and
attaches every new window to the persistent `main` tmux session. It uses the
latest stable FiraCode Nerd Font Mono release with contextual programming
ligatures explicitly disabled and a solid non-blinking bar cursor. Tmux remains
the authoritative interface for sessions, windows, panes, and Ctrl-click URL
handling while mouse reporting is active. Konsole and Alacritty remain
available as recovery and comparison frontends.

## Docker

The `docker_engine` feature configures Docker CE from Docker's official Ubuntu
APT repository. Kubuntu and WSL use the same engine packages and command-line
plugins. WSL runs its own daemon inside the distribution; the profiles do not
install Homebrew Docker clients and do not use Docker Desktop integration.

The WSL preflight runs before Docker package mutations. It requires systemd and
rejects a CLI or active socket injected by Docker Desktop, preventing two
engines from competing for the same CLI and context. Docker and containerd are
enabled through systemd.
The interactive user is appended to the `docker` group, so the first apply
requires a WSL restart or a normal Linux logout/login before that membership is
active in every shell.

## Tailscale

The `tailscale` feature is enabled only for the native Kubuntu profile. Its
Ansible role validates Tailscale's signing-key fingerprint, follows the stable
repository for the active Ubuntu release, installs the latest package, and
enables `tailscaled`.

Authentication is machine state, not portable configuration. Apply never
stores an auth key and never joins a tailnet silently; the user performs the
one-time browser enrollment with `sudo tailscale up`. Subsequent applies
preserve the daemon state and existing node identity.

The Windows profile records `Tailscale.Tailscale` for native installation.
Neither WSL profile installs Tailscale. This follows Tailscale's guidance to use
the Windows host client instead of nesting Tailscale traffic inside Tailscale
traffic, which can break connectivity.

## Adapters

`bin/dot` is the canonical command on Linux, WSL, and Termux. It resolves
profile inheritance before calling Ansible. It also has a direct mode used by
Ansible to install portable links idempotently.

`bin/dot.ps1` provides Windows prerequisite checks and configuration. It never
installs applications or prerequisites.

## JavaScript toolchain

Vite+ is the primary JavaScript toolchain entry point on common Linux profiles.
Its stable-channel ownership lives in `packages/vite-plus.yml`. Bootstrap
installs the latest stable release with Node-manager shell mutation disabled,
then generates the supported environment file under `VP_HOME`.

The shared shell configuration exports `VP_HOME` and places `VP_HOME/bin` on
`PATH`. Bash and Zsh source the generated environment after their completion
systems are available, enabling the `vp env use` current-shell wrapper and
dynamic completions. Generated runtimes, package managers, shims, caches, and
the environment file remain machine-local under `~/.vite-plus`.

## Neovim

Kubuntu and both WSL profiles use the same Neovim configuration from
`config/nvim`, linked at `~/.config/nvim`. Homebrew owns the latest stable
Neovim, Stylua, and Tree-sitter CLI releases so the editor version does not
depend on an older distribution package.

The configuration is deliberately modular and smaller than the retired
Kickstart fork. lazy.nvim loads a reviewed plugin set and `lazy-lock.json`
records a tested plugin graph. The lockfile is a compatibility artifact, not a
policy of permanently freezing versions: personal profiles test candidate
updates in isolated XDG directories and advance it automatically after the
candidate passes.

fzf-lua is the single fuzzy-picker interface. Oil owns directory editing,
Harpoon owns the short working-file list, and native undo plus the state
directory preserve editing history. Gitsigns, Diffview, and the existing
Lazygit CLI provide progressively deeper Git views. The UI remains conventional
and stable: GitHub Dark, Lualine, and Which-key, without message, dashboard, or
animation replacement layers.

Language support is curated for Lua, shell, Python, JavaScript/TypeScript,
HTML/CSS, JSON/YAML/TOML, Markdown, Docker/Compose, and SQL. Mason installs
their editor-local servers and tools; Neovim's current native LSP API owns
clients, Blink owns completion, Conform owns explicit formatting, and nvim-lint
owns diagnostics. Formatting is manual. Autosave is guarded against special,
unnamed, read-only, and non-file buffers.

The old `DovieW/nvim-config` repository remains unchanged as historical
reference. It is not deployed and is not a second source of truth.

## Fuzzy-picker interface

`config/fzf/fzfrc` is the shared presentation layer for every external FZF
surface. It deliberately contains only colors, borders, padding, indicators,
and selection styling. Shell widgets, `fzf-tab`, `dot`, Git helpers, and
PowerShell each choose geometry appropriate to their workflow.

Preview ownership follows the same boundary. The portable
`dot-fzf-preview` helper renders files with `bat` and directories with `eza`,
with standard-command fallbacks. Git and `dot` provide semantic previews of
their own, while history and SSH selection remain compact. Neovim's fzf-lua
uses the same visual language but retains native editor previews and
highlighting.

## Device identity and secrets

The first bootstrap writes a stable logical device ID to
`~/.config/dotfiles/device.json`. WSL derives its default from the Windows host
so Windows and WSL share one physical-device identity.

Bitwarden item names are deterministic:

```text
dotfiles/bootstrap-v1
dotfiles/ssh/<account>/<device-id>
```

The bootstrap item is a Secure Note whose notes contain JSON matching
`examples/bitwarden-bootstrap-v1.json`. SSH items use Bitwarden's SSH-key item
type. Kubuntu and Windows use Bitwarden's agent; WSL and Termux materialize the
same device key with mode `0600`. Git uses the public key file for SSH signing.

Bitwarden sessions are passed per command and are never written to startup
files. A session unlocked by `dot` is locked in a `finally` path.

## KDE

Only the reviewed allowlist in `bin/dot` is portable. KDE Wallet, recent files,
caches, session state, and KScreen's hardware identifiers are excluded. Every
replaced destination is backed up before a managed copy is installed, so KDE
and applications cannot mutate the repository during normal use.

The Kubuntu power policy never suspends automatically on AC, battery, or low
battery, and closing the lid does nothing. Pressing the physical power button
still suspends, as do explicit Sleep actions in the UI. PowerDevil owns the
live desktop behavior; a matching systemd-logind drop-in is the fallback if
PowerDevil is unavailable. Display topology remains host-local.

Performance policy is profile-specific: AC uses performance, battery uses
balanced, and low battery uses power-saver. Display brightness is set to 100%
on AC and regular battery. At 20% charge or below, PowerDevil selects the low
battery profile and sets display brightness to 40%. Kubuntu installs the NVIDIA
desktop driver currently marked recommended by `ubuntu-drivers`, without
hard-coding a driver branch, and keeps hybrid graphics in PRIME on-demand mode
so Intel drives the desktop while NVIDIA remains available for explicit workloads. On the
IdeaPad Pro 5 16IAH10, the optional `nvidia-powerd` Dynamic Boost daemon is
disabled because driver 595.84 crashes while querying the current PZCN55WW
firmware. This does not disable GPU acceleration or runtime D3 suspension; it
only removes Dynamic Boost's extra CPU/GPU power shifting under load. Reassess
the workaround after a future NVIDIA driver or Lenovo firmware update.

The Kubuntu desktop uses a full-width, always-auto-hidden native Plasma panel.
The native Kickoff launcher stays at the far left while two flexible spacers
approximately center the traditional Task Manager; the panel contains no pager
or Show Desktop widget. Meta opens Kickoff. Alt+Space opens a centered KRunner
instance whose Applications provider is the only enabled runner. The panel's
screen-edge highlight is disabled and its pointer activation delay is zero.
Meta+D and Plasma's native four-finger downward gesture expose the desktop.
GitHub Dark is a tracked KDE color scheme layered onto Breeze components, so no
third-party Plasma code is required.

Plasma 6.6 does not expose configurable touchpad gestures. The Kubuntu profile
therefore enables the InputActions KWin plugin and tracks its YAML configuration
in `config/inputactions/config.yaml`. The mapping follows Windows: three-finger
horizontal swipes cycle applications; continuous direction-specific
three-finger vertical controls track the fingers through the full volume range;
and four-finger horizontal swipes move between virtual desktops. Four-finger
down explicitly exposes the desktop and four-finger up explicitly restores the
windows. A state-aware adapter works around KWin 6.6 ignoring direct
`showDesktop(bool)` DBus calls while avoiding the nondeterminism of blindly
toggling KDE's Show Desktop action.

The volume gesture emits continuous media-key updates. Plasma's global
volume-change feedback is disabled in the tracked `plasmaparc`, preventing a
sound on every step while retaining the visual volume display.

InputActions follows the latest stable tags of its control-tool and KWin-plugin
repositories. Because the plugin links against KWin, the build state records
the installed KWin package version. A normal `dot update` rebuilds it whenever
either a stable InputActions release or KWin changes. Only libinput-backed
three- and four-finger gestures are used, so the optional udev rule granting
raw touchpad-device access is deliberately not installed.

The laptop's CIRQ1080 I2C Precision Touchpad is subject to libinput issue
[#1297](https://gitlab.freedesktop.org/libinput/libinput/-/work_items/1297):
bursts of otherwise regular reports can be misclassified as impossible jumps,
causing libinput to discard real motion. A tightly matched local quirk disables
only libinput's jump detector on the Lenovo 83JM. This is a temporary workaround
and must be removed once the upstream arrival-time fix reaches Ubuntu. It does
not change pointer acceleration, scrolling, gesture recognition, or the
firmware's palm classification.

Native Linux graphical applications receive
`SSH_AUTH_SOCK=${HOME}/.bitwarden-ssh-agent.sock` through systemd's
`environment.d` mechanism. This makes Obsidian and other desktop Git clients
use the same Bitwarden-held device key as interactive shells. Bitwarden starts
at login and must remain running and unlocked for SSH authentication or commit
signing; the private key is never materialized on Kubuntu.
