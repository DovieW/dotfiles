# Repository agent instructions

## “Finalize this computer” protocol

When the user says **“finalize this computer”**, **“finish setting up this
computer”**, or equivalent while working in this repository, treat it as the
defined device-finalization workflow. Do not interpret it as a request to
blindly apply the entire `kubuntu-laptop` profile.

1. Read `docs/finalize-computer.md` completely.
2. Run `bin/dot finalize prepare --profile <profile>` to refresh the local,
   privacy-bounded inventory and `~/.local/state/dotfiles/finalization-handoff.md`.
3. Inspect the handoff and inventory plus current live hardware using
   read-only commands. Distinguish automatically detectable policy from a real
   device-specific exception.
4. Create or update `devices/<device-id>.yml` using
   `devices/example-device.yml`. Never commit raw serial numbers, product UUIDs,
   credentials, tokens, private keys, vault data, or unredacted command output.
5. Prefer improving safe hardware detection in the shared implementation over
   adding a device exception. Keep a device override only for genuine firmware,
   peripheral, display, or intended-use differences.
6. Validate repository tests and the relevant targeted/check-mode behavior.
   Review every privileged or externally visible change before applying it.
7. Run `bin/dot finalize apply --profile <profile>` only after the tracked
   manifest accurately describes the reviewed machine.
   For native Kubuntu, confirm the early remote-support phase completed:
   Tailscale must be joined and normal key-only OpenSSH must be active. Do not
   substitute Tailscale SSH or place reusable private/auth keys on DOTBOOT.
8. Run `bin/dot doctor --profile <profile>`. Enrollment, authentication,
   reboot, attached-display, and other physical acceptance boundaries must be
   reported separately; do not disguise them as completed validation.
9. Commit and push the durable source changes with selective staging. Refresh a
   DOTBOOT USB only after freshly verifying its removable hardware identity and
   stable serial-based path. Never infer a destructive media target.

An absent device manifest means the computer is new/unfinalized. A finalized
manifest is the durable recognition record used by future installs and chats.
The generated handoff is local state and must not be committed.

If the user corrected the OS hostname after identity bootstrap, use
`bin/dot device rename OLD NEW --profile PROFILE`; do not delete device state or
create replacement credentials manually.
