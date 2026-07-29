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
- Snap is limited to curated Kubuntu desktop exceptions.
- Termux uses `pkg`.
- Windows manifests are records and never trigger application installation.

## Adapters

`bin/dot` is the canonical command on Linux, WSL, and Termux. It resolves
profile inheritance before calling Ansible. It also has a direct mode used by
Ansible to install portable links idempotently.

`bin/dot.ps1` provides Windows prerequisite checks and configuration. It never
installs applications or prerequisites.

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
replaced destination is backed up before linking.
