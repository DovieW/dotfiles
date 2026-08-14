# Finalize a computer

Bootstrap and finalization are deliberately separate.

The Linux USB launcher uses its checksummed Git bundle as an offline baseline,
then fast-forwards from the public GitHub repository when networking is
available. Once a fix is pushed, rerun the same `START-LINUX.sh` on the target;
do not shuttle the USB back and forth merely to obtain repository updates.

Bootstrap establishes identity, repositories, browser/password-manager access,
the agent runtime, portable configuration, and the safe operating-system
baseline. On an unregistered computer it defers machine-sensitive tags:

Before the long profile phase, bootstrap installs Tailscale, requires its
one-time browser enrollment, and configures key-only normal OpenSSH using the
public workstation keys published by the managed GitHub account. It prints the
stable Tailscale SSH target for remote troubleshooting. This is ordinary SSH
over Tailscale, not Tailscale SSH; no reusable private key or Tailscale auth key
is stored on DOTBOOT. Finalization refuses to complete if either endpoint is
not securely active.

- `anydesk`
- `gpu`
- `meshcentral`
- `nomachine`
- `touchpad`

This prevents a generic profile from applying assumptions learned from a
different laptop. Bootstrap generates these local, mode `0600` artifacts:

```text
~/.local/state/dotfiles/finalization-handoff.md
~/.local/state/dotfiles/finalization-inventory.json
```

The inventory intentionally excludes DMI serials, product UUIDs, credentials,
tokens, private keys, vault data, Tailscale addresses, and raw EDID data.

## New computer

If no tracked `devices/<device-id>.yml` exists, bootstrap offers new-computer
baseline mode. It can also be selected explicitly:

```bash
dot bootstrap --profile kubuntu-laptop --device-state new
```

After baseline completion, open a coding agent in the repository and say:

```text
Finalize this computer.
```

`AGENTS.md` defines that phrase as an executable repository workflow. The agent
refreshes the inventory, reviews live hardware, improves shared detection when
appropriate, writes the device manifest, validates it, and applies only the
approved deferred tags.

## Existing computer

A tracked finalized device manifest is the recognition record. Automatic mode
uses it when the logical device ID matches. Explicit restore is available with:

```bash
dot bootstrap --profile kubuntu-laptop --device-state existing
```

Existing mode refuses to continue without the manifest. It applies the same
safe baseline and then only that device's reviewed `approved_tags`.

## Commands

```bash
dot finalize prepare --profile kubuntu-laptop
dot finalize status --profile kubuntu-laptop
dot finalize apply --profile kubuntu-laptop
```

`prepare` is read-only apart from local state. `status` reports whether the
logical device is registered. `apply` requires a valid tracked manifest and may
perform privileged changes through the approved Ansible tags.

## Rename before finalization

If the operating-system hostname was corrected after identity bootstrap, use
the managed migration instead of deleting `device.json` or creating a second
key:

```bash
dot device rename OLD-ID NEW-ID --profile kubuntu-laptop
```

The command requires the rebooted system hostname to equal `NEW-ID`. It renames
the existing Bitwarden per-device SSH item, preserves its key material, updates
local signing paths and bootstrap state, and regenerates the finalization
handoff. Existing GitHub key labels may retain the historical name; labels do
not affect authentication or signing identity.

The manifest is not a replacement for automatic detection. AMD, Intel, and
NVIDIA graphics should be handled generically where reliable detection is
possible. Manifests record which deferred subsystems belong on a machine and
document only genuine exceptions.
