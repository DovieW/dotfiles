# Local Kubuntu diagnostics

The `diagnostics` feature is enabled by `kubuntu-laptop` and inherited by
`kubuntu-desktop`. Apply only this feature:

```sh
dot apply --profile kubuntu-laptop --tags diagnostics
dot-diagnostics health
```

Administrator authentication uses the existing dotfiles GUI authentication path.
This feature never edits Kolboo, restarts the audio stack, changes the active
microphone, records audio, deliberately crashes the host, or reboots it.

## What is collected

| Source | Frequency | Contents and limits |
| --- | --- | --- |
| General journal | Event driven | Existing app/kernel/service messages; 8 GiB, maximum age 30 days |
| Diagnostic journal | Event driven | Separate `diagnostics` namespace with 64 GiB on the IdeaPad and 1 GiB by default, a 60-day maximum age, and 30-second synchronization |
| Signals | Event driven | SIGKILL, SIGTERM and common fatal signals; generation result, sender context and target TID/name |
| Process exits | Event driven | Nonzero process-leader exit status and identity/start time |
| Kernel OOM | Event driven | `oom:mark_victim`; userspace memory-manager decisions remain in their service journals |
| Resources | 30 seconds | PCP numeric process/system metrics, pressure, disk/network counters, names and start identity |
| Audio | Native/Pulse subscriptions | Allowlisted PipeWire objects and Pulse event metadata; independent state queries every two minutes |
| Devices | Event driven | Selected udev properties and BlueZ connection/service-resolution transitions |
| Freeze evidence | Existing 30 seconds | Existing bounded root-only recorder; unchanged |
| Thread snapshot | Manual or severe I/O pressure | At most 10,000 thread states/wait channels, bounded kernel stacks; no userspace memory |
| Display resume | System sleep or laptop lid-open | Sleep and display events, built-in and external output state, and bounded KDE session queries for 30 seconds |
| Wake source | Before and after each system sleep | Kernel-reported wake interrupt, sleep transition markers, wake-source activations and ACPI interrupt count changes |
| Health | Ten minutes | Service states, recent heartbeats, actual signal canary, archive freshness, selected error/loss checks |

The services run indefinitely and survive reboot. **Sixty days is an age limit,
not a service expiry or a promise of minimum retained history.** Size caps can
shorten coverage. Journal namespaces have independent budgets, so application
chatter cannot evict the dedicated diagnostic stream. Native journal rotation
can temporarily exceed nominal size limits because active files are retained.
The IdeaPad allows up to 4,096 journal files so the file-count limit leaves
room for the 64 GiB budget with 32 MiB files.

The PCP wrapper makes hourly archives in `/var/lib/dot-diagnostics/pcp`, removes
completed archives older than 14 days or exceeding 4 GiB, compresses completed
archives, and preserves the active
archive. It checks every 30 seconds, so the cap is not a filesystem quota.
Sysstat remains an independent ten-minute baseline with 30-day history. Default
PCP logging, inference and proxy services are stopped; PMCD binds only loopback.
Core files remain under systemd-coredump, with 2 GiB storage and 10 GiB free-space
targets. Existing core age cleanup is owned by systemd-tmpfiles.

PCP records an explicit allowlist. Arguments (`proc.psinfo.psargs`), environment,
maps, current directories and arbitrary labels are excluded. Executable/process
names and existing application journals can still contain private information.
PCP's process instance names normally retain PID and argv[0], not arguments;
applications can set unusual argv[0] values. Bundles are private and must be
reviewed before sharing. No automatic upload, cloud account or subscription.

## Investigating an incident

```sh
# Mark the current time without capturing media.
dot-diagnostics mark

# Optional bounded thread snapshot; root is needed to read other processes.
sudo /usr/local/libexec/dot-diagnostics snapshot

# Unified private bundle; use explicit timezone offsets and a new directory.
sudo /usr/local/libexec/dot-diagnostics export \
  --since '2026-11-16T17:40:00-05:00' \
  --until '2026-11-16T18:10:00-05:00' \
  --output /var/lib/dot-diagnostics/incidents/example

sudo lnav /var/lib/dot-diagnostics/incidents/example/timeline.txt
sudo journalctl --namespace=diagnostics --since '20 minutes ago'
sudo pcp atop -a /var/lib/dot-diagnostics/pcp/ARCHIVE_PREFIX
```

Export includes original journal JSON, timestamp-merged text, overlapping PCP
archives and JSON summaries, bounded freeze records, saved snapshots, overlapping
display-resume captures, wake records, archived pstore records and core **metadata**. It excludes actual core/kernel memory
dumps. The manifest identifies post-incident queries and failed sources. Journal
exports stop at 200,000 records / 128 MiB per source and report truncation; use a
narrower window after a log flood. Resource JSON is included separately; pressure,
memory and top-RSS summaries are also merged into the text timeline.
Copying a currently active PCP archive is best effort; validate it with
`pmlogcheck` before relying on it. Exporting never deletes original evidence.
Freeze samples are limited to the requested interval and compressed in the
bundle. Saved thread snapshots may extend beyond the interval. These records can
contain process names. The caller owns retention of exported incident bundles.

### Display resume

The sleep target arms a private tracefs buffer with power and DRM events before
sleep. After wake the recorder saves the first batch of kernel events immediately
and samples for 30 seconds. It records connector and backlight state, display
pipes when DRM exposes them, KWin's active-output response, and whether
the lock screen responds. Generic DRM events report a controller index, which can
repeat across GPUs. Intel display events include the PCI device and pipe for
matching them to a connector. A completed display update is kernel
evidence only. Confirm the physical display and lock screen in person.

On laptops, a UPower lid watcher also arms the bounded buffer when the lid
closes and starts a capture when it opens while the system stays awake.
If a system sleep occurs too, the sleep hook owns dispatch and both events
are marked in the same capture. Repeated probe timeouts or a DRM controller
with a queued event and no observed delivery after three seconds can request
one bounded thread snapshot. That snapshot records kernel wait evidence.

Each record is flushed to a root-only JSONL file in
`/var/lib/dot-diagnostics/resumes`. The first record survives even if nothing
runs after resume. The next capture prunes files older than 14 days and retains
at most 20. The capture does not change display settings or collect screen
contents.

For physical acceptance, close and reopen the laptop lid while it stays awake,
then separately suspend and wake it. Check that the new files have the relevant
`lid_open` or sleep events, connector and session samples, and `complete`.
On a workstation without a lid, suspend and wake it and check that the new file
has `pre_sleep`, kernel sleep and display events, connector and session samples, and
`complete`. Compare to what appeared on the display. Inspect the capture status with
`journalctl --namespace=diagnostics -u dot-diagnostics-resume-arm.service -u dot-diagnostics-resume.service`.

### Wake source

The systemd sleep hook records each sleep attempt before the kernel transition
and saves wake evidence before systemd finishes the operation. Each attempt
has a private trace buffer and a before-and-after comparison of ACPI interrupt
counters. The post record includes the wake IRQ and its registered handlers
when the kernel reports an IRQ. Match the boot ID and boot-time timestamps to
the system journal. Trace activations, shared IRQs and ACPI counter increases
are candidates and can include activity during suspend preparation or resume.

Root-only JSONL files in `/var/lib/dot-diagnostics/wakes` rotate at 1 MiB per
file, retaining up to four files. The next capture prunes files last written
more than 30 days ago. This history is independent of display capture rotation.
The hook runs only at sleep boundaries and sends no network traffic.

The signal trace observes kernel signal generation, rather than only `kill()`.
The target is a **thread ID**. Sender PID identifies the execution context, which
is not necessarily the responsible actor for kernel-generated signals. Match
generation with exit records and memory-manager/service logs; generation alone
does not prove delivery or termination. Some fatal paths bypass signal generation.
Common fatal signals are selected; this is not a trace of every syscall.

Graph state cannot reveal every browser-internal permission/device-selection
failure. Listed devices do not prove capture works. Severe I/O pressure is
context, not proof of who sent SIGKILL. Complete hardware/kernel lockups can stop
every local collector, and buffer tails may not survive power loss.

## Health, verification and acceptance

```sh
systemctl status dot-diagnostics-{signals,devices,resources}.service
systemctl --user status dot-diagnostics-audio.service
dot-diagnostics health
sudo /usr/local/libexec/dot-diagnostics health
journalctl --namespace=diagnostics --since '5 minutes ago'
# Explicit live acceptance: terminates disposable children and induces OOM only
# inside its own tiny cgroup, never in the host or an existing application.
sudo ~/repos/dotfiles/scripts/verify-diagnostics
```

The health canary terminates only a new `sleep` child owned by that invocation,
then checks the **stored** signal event for matching sender and target IDs.
The user health timer also checks audio heartbeats/queries and sends a desktop
notification on failure. The root health report lives at
`/var/lib/dot-diagnostics/health.json`; the user report lives at
`~/.local/state/dotfiles/diagnostics/health.json`. A service being active is not
enough. Bpftrace stderr (including loss/load errors) goes to the diagnostic
journal. Pressure snapshots have a ten-minute cooldown. Snapshots are pruned by
the root health timer at 14 days / 1 GiB.

Required live checks: signal canary; ordinary and abnormal exits; pidfd/thread/
cgroup signaling; isolated cgroup OOM; audio collector restart/reconnection;
device state changes; archive replay and fake-secret inspection; rotation and
outage detection. A real reboot and physical suspend/device acceptance are
separate checks; never claim these from enabled unit files. Do not induce a host
OOM, force a crash or disconnect a working network for acceptance.

Measure CPU, resident memory, archive growth and writes over ordinary use, then
adjust intervals/budgets. No battery-life improvement or negligible-overhead
guarantee is implied. A scheduled timer does not wake the suspended laptop.

## Rollback

Stop/disable the `dot-diagnostics-*` system services/timer and the audio/health
user services/timer. Disable the display resume arm service to remove its sleep
target hook. Remove only this feature's named units, the
`70-dotfiles-retention.conf` drop-ins and `/etc/systemd/journald@diagnostics.conf`.
On the IdeaPad, also remove
`/etc/systemd/journald@diagnostics.conf.d/70-dotfiles-ideapad-retention.conf`.
Restore the backed-up PMCD options and previous sysstat history if desired.
Reload system/user managers and restart journald for changed retention policy.
Keep the existing crash/freeze setup and all collected evidence. Do not vacuum
the journal or delete archives as part of rollback. Set `diagnostics` false in a
device/profile policy before future full applies; disabling the flag alone does
not uninstall previously applied units. PCP and lnav may remain installed.

## Why these components

PCP provides configurable historical metrics; atop stores command arguments in
its raw history. Existing bpftrace and systemd provide a small event recorder
without a security-agent deployment. Lnav reads the merged timeline. Netdata,
Tetragon, Sysdig and LTTng are not additional always-on dependencies.

Sources:
- https://www.freedesktop.org/software/systemd/man/259/systemd-cat.html
- https://www.freedesktop.org/software/systemd/man/259/journald.conf.html
- https://pcp.readthedocs.io/en/latest/QG/QuickReferenceGuide.html
- https://github.com/performancecopilot/pcp/blob/7.1.1/src/pmdas/linux_proc/proc_pid.c
- https://bpftrace.org/docs/release_025/language
- https://docs.pipewire.org/page_man_pw-dump_1.html
- https://lnav.org/features
