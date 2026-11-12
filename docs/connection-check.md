# Connection Check

Apply with `bin/dot apply --profile kubuntu-laptop --tags connection-check`.
KDE profiles install a Connection Check application and pin it to existing task
managers when applied in an active graphical session. Existing pins are preserved.
For a later session, run `connection-check --pin`.

Click the wireless icon to start. The dialog shows signal/band, gateway and
internet ping averages and packet loss, DNS/HTTPS access, and measured download
speed. Details includes negotiated Wi-Fi rates and raw probe results. Repeated
launches cannot start overlapping checks.

The quick check downloads up to 10 MB. The optional longer test downloads up to
50 MB. Both have time limits; incomplete transfers are labeled. Latency probes
finish before downloads begin. Public probes use Cloudflare (1.1.1.1 and HTTPS);
gateway/interface detection uses the current IPv4 route. DNS uses the system
resolver. No connection settings are changed.

These are short samples, not guarantees of sustained speed. Blocked ICMP is
reported as missing ping responses rather than proof of no internet. Cellular
signal, upload, loaded latency and IPv6 are not measured. Other traffic and VPNs
can affect results. A detected route change asks you to rerun.

`connection-check --json` runs without a GUI; add `--long` for the larger sample.
