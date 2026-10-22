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
The form requires `firstname`, `lastname`, `email`, `phone`, `country` (lowercase
ISO code), `street`, `city`, and `state` (full name); `zip` is optional. Include
`policy` only with the user's consent to the registration notice. If the service
rejects an API request, use its official website and pass the downloaded ZIP
with `--archive`.
The download does not have an independently published checksum in this workflow.

For an explicit installer or update, save work and close Resolve, then run:

```sh
scripts/install-davinci-resolve --archive ~/Downloads/DaVinci_Resolve_VERSION_Linux.zip
```

The vendor's documented text-mode installer runs with administrator authorization
through passwordless sudo when available, otherwise the normal PolicyKit prompt.
Ubuntu's `t64` package names fail the vendor's legacy package-name check. The
helper bypasses that check only after verifying all four replacement packages
are installed and their real shared libraries load. GPU checks remain enabled.
The source ZIP is preserved. Existing installations are left alone during normal
apply; updates require an explicit archive. No app is automatically restarted,
no projects or preferences are removed, and no GPU drivers are changed.
The ordinary package post-update audit reports detectable stale processes;
plugins, bundled assets and interpreted code are outside its full coverage.
Check mode only checks executable availability and never launches the installer.

Verify the application-menu entry, launch Resolve, and check that the intended
GPU is available before calling the machine ready for editing. If a launch fails, inspect the actual
installer/logs before applying a compatibility workaround. Do not globally
replace system libraries or assume an installed executable proves GPU support.

## KDE display scaling

Resolve 21.1.1 on this Kubuntu installation ignored a Qt environment scale override
and did not give a useful result at native 175%. Its native 150% and 200% settings
produced visible changes; 150% was accepted on the 175% laptop display.
The `davinci-resolve` apply tag configures the native `DisplayScale` preference
using the closest of 100%, 150%, and 200% to the primary KDE display scale,
choosing the smaller value on a tie. It preserves other preferences and makes a
local backup before the first change. It never stops Resolve or edits its live
preferences: save and close the app before applying a different scale.

To apply just the scaling preference while Resolve is closed:

```sh
scripts/install-davinci-resolve --configure-display --ensure
```

Use `--check` instead of `--ensure` for a read-only comparison. If KDE display
information or the first-run preference file is unavailable, the helper reports
scaling pending. After a new installation, launch once and close Resolve, then
apply the tag again. Native scale choices and appearance may differ in future
Resolve releases, so verify visually after upgrades. No Qt scaling launcher override or system-wide Qt environment setting is installed.

## Hybrid Intel/NVIDIA graphics

On the IdeaPad, Resolve's CUDA processing initialized on NVIDIA while its shared
OpenGL context initialized on Intel Mesa. Opening a project then failed with
`Failed to register OpenGL object for CUDA interop` and `Packer OpenGL interop
failed`, followed by a misleading GPU-memory-full dialog at roughly 220 MiB total
NVIDIA usage out of 8 GiB. Successful CUDA startup alone did not prove a working
viewer.

The application-menu override uses NVIDIA's documented PRIME render-offload
variables (`__NV_PRIME_RENDER_OFFLOAD=1` and `__GLX_VENDOR_LIBRARY_NAME=nvidia`)
when `/usr/bin/nvidia-smi -L` succeeds. This keeps Resolve's OpenGL and CUDA on the
same NVIDIA GPU. Systems without an available NVIDIA GPU retain the vendor's
direct launch command. No driver or system graphics policy is changed. Launch
Resolve through its menu entry; launching `/opt/resolve/bin/resolve` directly
bypasses this application-specific setting. The NVIDIA launch was verified in
Resolve logs and the user reported the immediate warning no longer appeared
during the same initial use. After changing it, save work and
restart Resolve, then test opening a project and its viewer; startup alone is
insufficient validation.

Reference: [NVIDIA PRIME render offload documentation](https://download.nvidia.com/XFree86/Linux-x86_64/435.21/README/primerenderoffload.html).
