# FilmCraft on Kubuntu

Both Kubuntu profiles install the official standalone FilmCraft Debian package,
including `/usr/bin/filmcraft` and `/usr/bin/filmcraft-cli`. The desktop menu entry
is FilmCraft. This does not install ArtCraft Launcher or require a subscription.
The alpha editor is being evaluated alongside Resolve.

`packages/external-deb.yml` tracks `storytold/filmcraft` and its latest non-draft,
non-prerelease x86_64 Debian asset. The existing external-package resolver checks
GitHub's published SHA-256 digest. The dependency, install and running-process
audit paths are shared with the other external Debian apps:

```sh
bin/dot apply --profile kubuntu-laptop --tags app-updates
```

Use `kubuntu-desktop` on a desktop. That tag updates other managed applications
too. Save projects and reopen FilmCraft after an update; the updater does not
close it, discard work, start an inactive editor, or alter its preferences. The
post-update audit detects replaced executables and mapped libraries; it cannot
prove all bundled assets, plugins or interpreted code are current.

## MCP availability versus connection

The package includes an MCP server. With `filmcraft_mcp: true`, the managed
Kubuntu configuration registers a global Codex server named `filmcraft` and
overrides the FilmCraft menu launcher to enable its loopback bridge. This targets
the visible editor rather than a separate headless project. Apply only this
configuration with:

```sh
bin/dot apply --profile kubuntu-laptop --tags filmcraft
```

Use `kubuntu-desktop` on a desktop. This configuration does not install the
package by itself, start an inactive editor, or restart either application.
Save and reopen FilmCraft after changing the menu launcher. Codex reads the
registration from `~/.codex/config.toml`; a running assistant may need its MCP
configuration refreshed before native tool names appear. The live CLI bridge
can be used immediately without restarting the assistant.

- `filmcraft-cli mcp` starts a headless MCP session over stdio.
- To operate a visible editor, start `filmcraft --control 9876`, then use
  `filmcraft-cli mcp --bridge 127.0.0.1:9876` as the assistant's MCP command.
- Do not accidentally use a separate headless project when intending to edit
  the project in the visible window. Test an inspect/read operation first.
- The bridge listens on loopback and can operate with the user's file access;
  it runs only while FilmCraft is open. Set the profile feature off and remove
  the menu override and Codex registration if you no longer want the connection.

Initial verification on the IdeaPad used 0.10.0 (Debian version 0.10.0-1): the
editor launched, startup detected NVDEC, and a headless MCP initialize/tools-list
exchange returned the FilmCraft server identity and 17 tools. A subsequent live-bridge check successfully initialized MCP, listed 17 tools,
and read the visible editor's project and sequence with `doc_inspect`. Codex's
registration was validated and a targeted real/check apply converged without
changes. This did not test an actual edit/export.

References: [FilmCraft](https://getartcraft.com/apps/filmcraft),
[agent documentation](https://github.com/storytold/filmcraft/blob/main/docs/agents.md).
