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
- Snap is exception-only and no application is currently managed through it.
- Termux uses `pkg`.
- Windows manifests are records and never trigger application installation.

Program manifests declare ownership, source, and release channel rather than
freezing workstation versions. Apply upgrades managed APT, Homebrew, external
Debian, Snap, and Termux packages to the latest stable releases their providers
offer. Native supported updaters such as `vp upgrade` are valid and do not
create dotfiles drift. Project dependency lockfiles and project runtime pins
remain authoritative inside each project.

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
balanced, and low battery uses power-saver. Kubuntu installs the NVIDIA desktop
driver currently marked recommended by `ubuntu-drivers`, without hard-coding a
driver branch, and keeps hybrid graphics in PRIME on-demand mode so Intel drives
the desktop while NVIDIA remains available for explicit workloads. On the
IdeaPad Pro 5 16IAH10, the optional `nvidia-powerd` Dynamic Boost daemon is
disabled because driver 595.84 crashes while querying the current PZCN55WW
firmware. This does not disable GPU acceleration or runtime D3 suspension; it
only removes Dynamic Boost's extra CPU/GPU power shifting under load. Reassess
the workaround after a future NVIDIA driver or Lenovo firmware update.

The Kubuntu desktop uses a full-width, always-auto-hidden native Plasma panel.
Two flexible spacers approximately center the traditional Task Manager; the
panel contains no launcher, pager, or Show Desktop widget. KWin's
modifier-only shortcut maps Meta directly to a centered KRunner instance whose
Applications provider is the only enabled runner; Alt+Space remains a fallback.
Meta+D and Plasma's native four-finger downward gesture expose the desktop.
GitHub Dark is a tracked KDE color scheme layered onto Breeze components, so no
third-party Plasma code is required.
