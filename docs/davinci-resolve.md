# DaVinci Resolve on Kubuntu

Both Kubuntu profiles enable the free Linux edition with `davinci_resolve`.
Blackmagic targets Rocky Linux, so Kubuntu compatibility and GPU operation must
be verified on each machine. The proprietary Studio edition is not installed.

Run `bin/dot apply --profile kubuntu-laptop --tags davinci-resolve` (or use
`kubuntu-desktop`). This installs runtime dependencies and runs the official
installer when exactly one `DaVinci_Resolve_*_Linux.zip` is in `~/Downloads`.
Without an archive it reports installation pending; prerequisites alone do not
mean Resolve is installed. Obtain the ZIP through Blackmagic's support page:
https://www.blackmagicdesign.com/support/family/davinci-resolve-and-fusion
Registration information is never stored in this repository. An agent can handle
registration and the download with `scripts/install-davinci-resolve --download`,
passing the vendor form JSON on stdin. This resolves the newest stable free Linux
release, downloads from Blackmagic over HTTPS and checks ZIP integrity. Supply
only user-authorized registration details; never invent them or persist them.
The download does not have an independently published checksum in this workflow.

For an explicit installer or update, save work and close Resolve, then run:

```sh
scripts/install-davinci-resolve --archive ~/Downloads/DaVinci_Resolve_VERSION_Linux.zip
```

The vendor installer presents its own license and administrator authorization.
The source ZIP is preserved. Existing installations are left alone during normal
apply; updates require an explicit archive. No app is automatically restarted,
no projects or preferences are removed, and no GPU drivers are changed.
The ordinary package post-update audit reports detectable stale processes;
plugins, bundled assets and interpreted code are outside its full coverage.
Check mode only checks executable availability and never launches the installer.

Verify the application-menu entry, launch Resolve, and check that the intended
GPU is available before calling the machine ready for editing. If the vendor's
installer rejects Debian package names or a launch fails, inspect the actual
installer/logs before applying a compatibility workaround. Do not globally
replace system libraries or assume an installed executable proves GPU support.
