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

The package includes an MCP server. It still needs to be registered with the
chosen assistant; installing the editor does not connect this chat to it.

- `filmcraft-cli mcp` starts a headless MCP session over stdio.
- To operate a visible editor, start `filmcraft --control 9876`, then use
  `filmcraft-cli mcp --bridge 127.0.0.1:9876` as the assistant's MCP command.
- Do not accidentally use a separate headless project when intending to edit
  the project in the visible window. Test an inspect/read operation first.
- The bridge listens on loopback and can operate with the user's file access;
  leave it disabled when it is not needed.

Initial verification on the IdeaPad used 0.10.0 (Debian version 0.10.0-1): the
editor launched, startup detected NVDEC, and a headless MCP initialize/tools-list
exchange returned the FilmCraft server identity and 17 tools. This did not test
an actual edit/export or register a client connection.

References: [FilmCraft](https://getartcraft.com/apps/filmcraft),
[agent documentation](https://github.com/storytold/filmcraft/blob/main/docs/agents.md).
