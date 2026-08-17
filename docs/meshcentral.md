# MeshCentral agent

The Kubuntu profile supports the native MeshCentral agent without putting a
server invitation, device-group identifier, or enrollment token in this public
repository.

Normal `dot apply` runs are deliberately conservative. They install the HTTPS
prerequisites and keep an already-enrolled `meshagent.service` enabled and
running. They do not silently enroll the machine or move it between device
groups.

## Enroll this laptop

In MeshCentral, open the destination device group, choose **Add Agent**, select
Linux, and copy the complete generated install command. Then run:

```bash
dot apply --profile kubuntu-laptop --tags meshcentral
dot meshcentral enroll
dot meshcentral status
```

Paste the complete generated command at the hidden prompt. The command is
parsed as enrollment data; it is never evaluated by a shell, written to disk,
or retained after enrollment. The validated HTTPS server origin, same-origin
installer URL, and device-group identifier are passed to the installer as
fixed arguments.

`dot meshcentral enroll` downloads the current installer directly from the
configured MeshCentral server, invokes it, and verifies the system service.

For repeatable enrollment, the invitation can optionally be stored as the
Bitwarden secure note `dotfiles/meshcentral-agent`:

```bash
dot secrets meshcentral-agent
dot meshcentral enroll-stored
```

The default enrollment path deliberately does not depend on Bitwarden.

If a stored invitation was created by the legacy parser that truncated IDs at
`$` or `@`, replace it and enroll the current computer in one pass:

```bash
dot meshcentral enroll-and-store
```

Paste the current Linux install command when prompted. The validated values
replace the Bitwarden note before the installer runs; neither the command nor
the device-group identifier is written to dotfiles.

## Maintenance

```bash
dot meshcentral status
dot doctor --profile kubuntu-laptop
dot apply --profile kubuntu-laptop --tags meshcentral
```

MeshCentral publishes agent updates through the server-agent relationship, so
the package is not added to the APT or Homebrew manifests. Re-enrollment is an
explicit operation.

The upstream MeshAgent documents some Linux desktop-control limitations,
especially under Wayland. Inventory, terminal, files, and other agent features
can still work even when interactive desktop control is constrained by the
display session.
