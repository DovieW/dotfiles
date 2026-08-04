# Homelab integration

Workstations and infrastructure have deliberately separate sources of truth:

- Public `DovieW/dotfiles` owns local clients, the `dot homelab` adapter,
  Bitwarden retrieval, and the FZF interface.
- Private `DovieW/homelab-infra` owns the reviewed TrueNAS inventory and the
  authoritative tailnet policy.
- Application repositories continue to own their compose files, secrets, and
  lifecycle tooling.

## Day-to-day commands

Run `dot homelab` for the complete described FZF menu, or call actions directly:

```bash
dot homelab status
dot homelab doctor
dot homelab diff truenas
dot homelab diff tailscale
dot homelab apps
dot homelab backups
dot homelab sync
```

These operations are read-only. Remote changes require an explicit target:

```bash
dot homelab apply truenas
dot homelab apply tailscale
dot homelab rollback truenas RUN_ID
dot homelab rollback tailscale RUN_ID
```

An apply prints the exact diff, creates an owner-only pre-change backup under
`~/.local/state/homelab-infra/backups`, and requires the operator to type a
target-specific confirmation. The first release can only start or stop managed
services/applications and publish a validated tailnet policy. Storage, shares,
snapshots, upgrades, and deletion remain audit-only.

Rollback is restricted to that same narrow mutation set. It previews the
restoration, creates a fresh pre-rollback backup, and requires the exact typed
confirmation `rollback TARGET`. There is no unattended confirmation bypass.

## Credentials

Use a scoped Tailscale OAuth client, not an expiring user API token:

```bash
dot secrets tailscale-oauth
```

The command validates policy read access, stores the client ID and secret in
`dotfiles/tailscale-oauth`, and moves the superseded `dotfiles/tailscale-api`
item to Bitwarden trash. One-hour access tokens are minted in memory.

Create separate TrueNAS 25.10 JSON-RPC identities and store them independently:

```bash
dot secrets truenas-api --role audit
dot secrets truenas-api --role operator
```

TrueNAS ships with a self-signed `localhost` certificate. Credential setup
shows its SHA-256 fingerprint and asks for a one-time `trust` confirmation.
The exact certificate is then pinned in Bitwarden. Routine commands remain
encrypted and automatic, while an unexpected certificate change is rejected
before an API key is sent. No private CA setup or global insecure TLS setting
is required.

The audit identity handles status, doctor, diff, and inventory. The operator
identity should have only the service/application runtime permissions needed by
the supported apply path. SSH is retained for bootstrap and break-glass work,
not routine management.

No secret is loaded by shell startup, printed, placed in command arguments, or
written to either Git repository.
