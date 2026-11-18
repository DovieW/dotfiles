# Network Quality Test

Apply with `bin/dot apply --profile kubuntu-laptop --tags connection-check`.
KDE profiles install Network Quality Test in the Start menu without pinning it to
the taskbar. Search for **Network Quality Test**, Wi-Fi, hotspot, speedtest, ping,
latency, or internet. The launcher includes these search keywords and absolute
executable/icon paths so it works with the desktop session's minimal PATH.
The command remains `connection-check`.

Launch Network Quality Test to start. The dialog shows an overall verdict and
rates each measurement **Good**, **Fair**, **Poor**, or **Unrated**. The thresholds
beside each result are quick guides. Router latency describes the local path,
while internet latency measures a round trip to Cloudflare. Fair falls between
the Good and Poor cutoffs. The download thresholds of 5 and 25 Mbps are rough
reference points for an HD and 4K stream, respectively.
[FCC streaming estimates](https://docs.fcc.gov/public/attachments/fcc-15-10a1.pdf)

Details includes negotiated Wi-Fi rates and raw probe results. Repeated
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
