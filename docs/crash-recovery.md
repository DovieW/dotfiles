# Chrome recovery and laptop freeze evidence

For continuous signal attribution, audio/device metadata, private resource
history, protected journal retention and incident exports, see
[Local Kubuntu diagnostics](diagnostics.md). The `diagnostics` tag complements
the existing `recovery` tag.

Install the scoped policy with `dot apply --profile kubuntu-laptop --tags recovery`.
This does not restart Chrome or reboot the laptop. A normal reboot is required
after first installing kdump, followed by `sudo kdump-config show` and a check
that `/sys/kernel/kexec_crash_loaded` contains `1`. No deliberate crash test is
performed. Ubuntu's default kdump loader enables `kernel.panic_on_oops=1` when
armed. The paired IdeaPad and desktop also enable the hard-lockup dump policy
through the `diagnostics` tag.

## Chrome backups

`dot-chrome-recovery.timer` runs every five minutes while the user manager is
running, including one catch-up run after login. It reads each Default/Profile N
profile's Sessions and Sync Data without stopping, closing, or modifying Chrome.
It does not back up cookies, passwords, the complete profile, or unsaved forms.
Sync records themselves can contain private browsing information and secrets:
keep the store private and never commit it or upload it unredacted.

The private store is `~/.local/state/dotfiles/chrome-recovery/`. Retention keeps
the newest five automatic generations, the last generation from each UTC day
within the newest generation's 30-calendar-day window, and all explicitly pinned
generations. At five-minute intervals, the five recent automatic snapshots cover
roughly the last 20 minutes. Older automatic snapshots are removed after a new
snapshot is successfully saved; days without snapshots have no daily backup.
Identical files are hardlinked between backups, never to the Chrome originals.
Do not edit backup files in place: export an independent copy first.

```sh
dot-chrome-recovery snapshot --pin
dot-chrome-recovery list
dot-chrome-recovery verify GENERATION
dot-chrome-recovery export GENERATION --destination /path/to/new-recovery-directory
systemctl --user status dot-chrome-recovery.timer dot-chrome-recovery.service
```

The first command pins the current state until manually removed. Pin an important
known-good session before a migration or risky change. Routine snapshots do not
automatically pin a potentially blank post-crash session. Corrupt/empty files
are preserved as forensic evidence and marked invalid, not repaired. The tool
checks file hashes and SNSS record framing, not whether Chrome can successfully
restore every tab. Counts of navigation commands are not tab counts.

Each live copy is accepted only if file identities, sizes, and change times
remain unchanged across copying, with three bounded attempts. This is still
**not a transactional LevelDB backup**, nor can it capture changes Chrome has
not flushed to disk. The copied Sync files are an additional forensic fallback.
A failed capture does not replace or prune older published generations.
A failed scheduled capture also requests a desktop notification.

## Memory-pressure priorities

The headless Codex Remote Control daemon runs as the normal desktop user inside
a root-owned system-service cgroup. That ownership boundary is intentional:
systemd-oomd ignores `ManagedOOMPreference=avoid` for a user-owned candidate
when swap exhaustion triggers victim selection. The service also uses a soft
70% `MemoryHigh` throttle, elevated CPU and I/O weights, and a negative kernel
OOM score. None of these settings makes Codex unkillable; they preserve an
emergency path when it is the only viable process left.

The managed Chrome launcher sets a positive kernel OOM score so a new Chrome
process is preferred over Codex during a kernel OOM. Existing Chrome processes
keep the score with which they started. systemd-oomd does not use that per-process
score; its corresponding protection comes from the root-owned Codex cgroup.

Desktop-owned Codex app servers remain in the graphical login session and are
not moved into the headless system service. This avoids two app-server owners
fighting over one control socket. On those profiles the policy still makes new
Chrome launches easier for the kernel to reclaim, while the normal desktop app
continues to own Remote Control.

Exports require a new directory outside the live Chrome profile and backup store.
They do not restore automatically. If recovery is needed, first preserve the
failure state, choose a pre-failure generation, and test its session files in
an isolated offline Chrome profile before replacing anything in the real profile.
Do not repeatedly reopen Chrome or blindly copy the whole Sync database back.
These are same-disk snapshots, not protection from drive failure or laptop loss.

## Freeze evidence

The root service `dot-freeze-recorder` samples every 30 seconds: memory, swap/VM
counters, disk counters, PSI, and up to 100 blocked threads including wait channel
and kernel stack if accessible. It avoids process command lines, environment,
and browser URLs. Data stays root-only in `/var/lib/dot-freeze-recorder/`, with
14 files of approximately 16 MiB each. Each record is flushed and fsynced.
Kernel restrictions can still prevent stack reads. Journald stays persistent
and flushes at 30-second intervals. Neither guarantees logs during a total lockup.

EFI pstore, if already supported by firmware/kernel, is left intact; systemd
archives records in `/var/lib/systemd/pstore/`. Kernel dumps go to the root-only
`/var/lib/dot-kdump/` and keep the latest three. Do not share raw memory dumps.
The standard Ubuntu kdump GRUB fragment owns the memory reservation; other boot
flags and the laptop's manual-first sleep/hibernate policy remain unchanged.

If the screen freezes but existing SSH still works, from a trusted Tailscale
device connect with `ssh dovie@dovie-ideapad-linux`, then:

```sh
sudo /usr/local/libexec/dot-freeze-recorder --once
sudo sh -c 'echo _wlm > /proc/sysrq-trigger'
sudo journalctl --sync
```

`w/l/m` requests blocked tasks, CPU backtraces, and memory information; it does
not kill processes or reboot. It can briefly interrupt CPUs and print a lot.
Privileged `/proc/sysrq-trigger` works independently of the keyboard mask.
The existing keyboard mask 176 permits S/U/B, not the complete R/E/I/S/U/B.
Do not trigger `c` (a deliberate kernel crash) without a separately planned test.

After a reboot preserve previous-boot journals, the recorder files, pstore,
and any kernel dump before troubleshooting. An abrupt journal end, graphics
warnings, or high I/O PSI alone does not establish a root cause.

## Hard lockups and peer observation

On the paired IdeaPad and desktop, `dot-hardlockup-dump.service` enables
`kernel.hardlockup_panic=1` when the NMI watchdog and crash kernel are both
available. A detected hard CPU lockup can end the current session and run
kdump. A display stall or a firmware lockup may produce no watchdog event.
Verify the armed state with `cat /sys/kernel/kexec_crash_loaded` and
`sysctl kernel.nmi_watchdog kernel.hardlockup_panic`.

Each `dot-crash-peer.service` reads the other machine's Linux and KWin
heartbeats over one SSH stream. Three consecutive KWin timeouts or loss of
the stream can request a thread and CPU-stack snapshot. Evidence is stored on
the observing machine in `/var/lib/dot-crash-peer`, with up to 20 private
captures. A connection loss can be sleep or a network outage. The observer
records a peer reboot or sleep interval when its next heartbeat confirms one.
If the desktop is frozen and SSH is still reachable, run
`/usr/local/libexec/dot-crash-peer grab` on the IdeaPad. The same command on
the desktop requests a capture from the IdeaPad.

Check `journalctl --namespace=diagnostics -u dot-crash-peer.service` on the
observing machine. These checks need an awake observer and a working network
path to obtain a snapshot. A dump can still be written locally if the watchdog
detects a hard lockup while the peer is unavailable.

The tracked `config/diagnostics/crash-peers.json` contains the paired hosts,
pinned host keys, and enrolled observer public keys. The corresponding private
key stays on its own machine under `~/.local/state/dotfiles/crash-peer/`.
The managed SSH entry confines the peer key to its Tailscale address and to
status streaming or the rate-limited snapshot. Re-enroll keys in the manifest
after a reinstall or host key change. Apply the `diagnostics` tag on both hosts.
To suspend this policy on a paired host, disable and stop
`dot-crash-peer.service` and `dot-hardlockup-dump.service`. To revoke a peer,
remove its `dot-crash-peer-managed` entry from the receiving host's
`~/.ssh/authorized_keys` and update the pairing manifest.

References: [Ubuntu kdump](https://ubuntu.com/server/docs/how-to/software/kernel-crash-dump/),
[kernel SysRq documentation](https://docs.kernel.org/admin-guide/sysrq.html).
