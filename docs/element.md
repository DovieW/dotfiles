# Element Desktop

The Kubuntu laptop profile (and desktop profile through inheritance) installs
Element Desktop from its official stable APT repository. Apply only this app with:

```sh
bin/dot apply --profile kubuntu-laptop --tags element
```

Use `--check` to preview repository configuration without installing or restarting
anything. Package installation is skipped in check mode because a new repository
is not yet available to APT. The tracked vendor key is scoped with `Signed-By`;
its primary fingerprint is `12D4CD600C2240A9F4A82071D7B0B66941D01538`.
Source: https://element.io/en/download

Updates preserve the user's Element configuration and never start an inactive app
or automatically restart a running one. Save work and fully quit/reopen Element
after an update to activate its Electron executable, shared libraries, and bundled
JavaScript/assets. Element has no separately managed system daemon. The existing
post-update process audit also runs for the `element` tag; it can report replaced
executables/libraries but cannot prove that interpreted code, plugins, or bundled
assets are current. Incomplete process access is reported as incomplete coverage.
Account login and encrypted-session verification remain interactive steps.
