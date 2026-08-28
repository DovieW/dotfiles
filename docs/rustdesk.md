# RustDesk client

The `kubuntu-laptop` profile installs RustDesk only for initiating connections
to other machines. It uses the official stable AppImage, verifies the
provider-published SHA-256 digest, and extracts it into the user's managed
application directory so FUSE is not required.

The native Debian package is intentionally not used because it registers and
starts `rustdesk.service`. This profile does not install, enable, or start a
RustDesk host service. Launch RustDesk from Plasma when an outbound connection
is needed.

```bash
dot apply --profile kubuntu-laptop --tags rustdesk
scripts/install-rustdesk-client --check
```
