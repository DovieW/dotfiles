# IdeaPad battery telemetry

`dot-charge` controls the firmware. The separate `dot-charge-telemetry.service`
records what the laptop reports. A collector failure leaves the schedule and
temporary overrides in effect.

## Commands

```sh
dot-charge history --range 24h --limit 40
dot-charge stats --range 7d --group daily
dot-charge stats --range 30d --group weekly --json
dot-charge stats --range 90d --group monthly --json
dot-charge stats --range lifetime --json
dot-charge report > battery-report.json
dot-charge export --range 30d --format csv > battery-30d.csv
dot-charge export --since 2026-11-18 --before 2026-11-25T07:09:56-05:00 --format json
journalctl -u dot-charge-telemetry.service -u dot-charge-telemetry-backup.service
```

`--range` accepts `24h`, `7d`, `30d`, `90d`, and `lifetime`.
Explicit ISO timestamps override the range endpoints. Dates and times without
an offset use the reporting machine's local zone. Daily, weekly and monthly
buckets use its local calendar. Weeks start on Monday. The export preserves
each observation's UTC timestamp and the capture zone and boot ID when known.
CSV embeds arrays and objects as JSON. An empty CSV field or JSON null denotes
an unavailable value.

`report` is the compact JSON input for another analysis tool. It includes
the historical baseline, lifetime and recent live statistics, capacity trends,
adapter fingerprints, charging curves, deadline and conservation outcomes,
uncertainty, version counts, and significant anomalies. It contains aggregates
and a bounded selection of recent events. Use `export` for individual rows.
The baseline normally ends at the earliest retained scheduler start. An
explicit `--baseline-before` can identify a known policy change if the
journal has rotated. Historical firmware policy can still be unknown.

## Collection

- Awake samples run about once a minute while charging and every five minutes
  otherwise. AC, charging state, power profile, actual mode and policy changes
  can trigger additional samples. The collector has no wake timer. A separate
  hook attempts one sample on each side of sleep with a one-second timeout.
  It makes no D-Bus calls and takes no inhibitor. Boot, collector lifecycle and
  shutdown requests are recorded when observable. After a crash, an absent
  shutdown record leaves the cause of the interruption unknown.
- BAT0 supplies gauge SOC, status, stored energy, full/design capacity, voltage,
  cycle count and the firmware's selected charge type. Health is full capacity
  divided by design capacity. Positive W and A mean charging. Negative values
  mean discharging. When current is unavailable, signed W divided by battery
  voltage gives an estimated current. Each field carries its unit in the name.
- UCSI identifies an online USB-C source and reports port, PD type, voltage and
  current limits when present. Their product uses the driver's fixed-profile
  maxima, which can come from different advertised profiles. For PD, the
  driver's current-now value is an operating current request. A 5 A request
  with unavailable voltage identifies a PD fingerprint with unknown wattage.
  Partner vendor and product IDs are captured only when Linux exposes them
  and the connector can be matched to the active UCSI supply. Generic AC
  without an online UCSI source is `mains_unidentified`. A fingerprint can
  group similar observations, with exact charger identity still unknown.
  [Linux UCSI power-supply driver](https://github.com/torvalds/linux/blob/v7.0/drivers/usb/typec/ucsi/psy.c)
- Battery temperature can come from a battery-specific sysfs, hwmon or valid
  UPower sensor. This IdeaPad exposes no verified pack temperature or internal
  resistance. CPU temperatures come from the CPU hwmon driver. CPU load is
  derived from adjacent `/proc/stat` counters. GPU runtime state uses cached
  kernel metadata. GPU utilization and temperature are unavailable through
  the passive interfaces used here. The service opens no GPU device.
- The initial import reads the matching internal battery's retained UPower SOC,
  unsigned rate, voltage, and time-to-full and time-to-empty series. It also
  preserves available boot and suspend boundaries from the local journal.
  It keeps original sample timestamps and leaves the original files in place.
  Older points retain their UPower provenance. Conflicting values for the
  same second are preserved as events and excluded from interval estimates.
  Their adapter, pack condition,
  temperature, mode, and workload are generally unknown.

## Interpreting the report

Individual readings are observations. Time and Wh between readings are
estimates. Duration and energy use linear interpolation only within adjacent,
compatible intervals. For live samples the maximum gap is twice the shorter
sampling period. For the event-driven UPower history it is five minutes.
Clock changes, detected sleep, reboot, collector restarts, adapter transitions
and changes in charging policy break continuity. The JSON report includes
per-metric coverage, unknown duration, and the largest gaps. A zero measured
total requires checking its coverage. Pack voltage uses 0.25 V bins, with
separate AC exposure above 16.8, 17.0 and 17.2 V. These cutoffs describe
exposure. AC discharge estimates have a per-adapter denominator for covered
time with both a known AC state and valid signed power.

### Sleep and comparisons

Each paired pre-suspend and post-resume record provides battery gauge endpoints,
an observed net stored-energy change, and known AC and firmware context.
The boot and monotonic clocks identify elapsed sleep. Recorded AC or policy
changes, a changed gauge reference, conflicting power evidence, or missing
endpoints prevent tighter bounds. A scheduled transition inside sleep is a
plan. Evidence of a timer expiration and a verified firmware change is
recorded separately.

The unconditional gap bounds are zero to the duration of the gap. Conditional
bounds assume that the endpoint AC connection and firmware mode held through
sleep, apart from a verified change at resume, and that stored energy moved
in one direction. A single unchanged USB-C
source with a positive reported fixed-profile limit can additionally bound
how quickly the battery could gain energy, assuming it stayed within that
limit. Timing gates use gauge rounding and the measured stored energy.
Missing charger data, including a zero reported voltage, supplies no power
ceiling. Stored-energy change is net change. Gross charging, cumulative
discharge and the timing of hidden reversals remain unknown.

Conditional bounds add zero seconds to sample-supported coverage. Each report
includes full-period exposure envelopes for comparison, given the same
covered-interval interpolation and a range for missing time. Use the
unconditional envelope to compare periods with different amounts of
missing data. Overlap, different power/workload context, or assumptions
accepted for only one period can make the comparison inconclusive. There
is currently insufficient full-charge curve data to infer overnight completion
times from a historical average.

### Full charge, wake attempts, and conservation

Equivalent full cycles divide estimated discharged Wh by the design Wh recorded
for that interval. The reported pack cycle count is separate. Capacity slopes
use daily median full-capacity estimates. Gauge recalibration and the coverage
of discharged energy affect these slopes, especially over a short baseline.

Charging segments report elapsed time to the first qualifying observation of
90%, 95%, 98% and 100%, grouped by observed adapter, starting SOC and CPU
workload. A genuine full reading requires SOC 100% plus the gauge's Full status
or Full capacity level with charging stopped. Older UPower data requires the
explicit Full state.
A segment can start after charging has already begun or end before full charge.
The 98% to full report includes elapsed time between the first observations
and crossing bounds when an earlier sample below 98% and a subsequent full
sample bracket the tail. Partial tails stay out of the per-adapter summary.
The CPU threshold for a heavy workload is 70% across the sample interval.
Deadline reports distinguish observed success, estimated misses, an observed
80% override and unknown outcomes. Headroom is measured from the first
observed full reading to the deadline. Check the unknown count alongside any
success rate.

The scheduler journals when its existing realtime wake timer is armed,
expires or is cancelled by a clock change. Sleep hooks read available RTC
wake alarms and the kernel's resume IRQ. The raw RTC interface can be empty
even with a timerfd alarm armed. A resume near an armed deadline establishes
timing correlation. It can also have an independent wake source. The
[existing wake-source diagnostics](diagnostics.md#wake-source) can supply
additional IRQ context. The deadline report lists evidence such as AC absent
near the deadline, still charging near the deadline, or still asleep beyond
the planned alarm. Where telemetry cannot distinguish causes it says so.

Conservation episodes track a sampled switch into Long_Life above 80%,
including whether the first observation was genuinely full, and any
sample-supported continuation of charging on AC. A gap or mode/wall-power
transition censors the duration. For a complete episode, the last sample
above 80% and the first at or below 80% bracket the time spent above it.

A future adaptive policy needs repeated verified full charges and conservative
completion bounds for each adapter and workload, including the final taper.
The current controller uses the local schedule and overrides while the data
accumulates.

## Local retention and recovery

The versioned database lives in `/var/lib/dot-charge/telemetry/battery.sqlite3`.
Root writes it. The laptop owner's primary group can read it. The raw history
is retained for the lifetime of the database. The daily timer uses the SQLite
backup API, checks the snapshot with `quick_check`, verifies a compressed
round trip, and keeps seven daily and four weekly copies under `backups/`.
Wake alarms and network transfers are unnecessary. The snapshots share the
laptop's disk failure risk. [SQLite Online Backup API](https://www.sqlite.org/backup.html)

To check a backup, run `dot-charge verify-backup /path/to/backup.sqlite3.gz`.
It computes the compressed SHA-256 and checks the decompressed database's
integrity, schema version, count and newest record using a private temporary
file. For a deliberate restore, stop the
collector, preserve the live database, and install the verified file at the
same path with owner `root`, the laptop owner's group, and mode `0640`.
Restart the collector and check `dot-charge history`. Review data and backup
sizes after roughly 30 days of normal use to size secondary telemetry
retention using observed growth.

### Off-device copy on TrueNAS

The IdeaPad can reach the existing bookmarked TrueNAS SMB share. The
homelab maintenance backups store NAS configuration state. Battery history
needs its own off-device copy.

Use a private TrueNAS dataset or directory on a private SMB share for
`IdeaPad/battery`. Copy the most recent verified `daily-*.sqlite3.gz` from
the backup directory over the home LAN. Copy to a temporary name on the share,
read it back locally, and run `dot-charge verify-backup` on both copies.
Matching SHA-256 and integrity results establish a recoverable copy. Then
rename the remote file to its dated name. An occasional weekly copy with a
TrueNAS periodic snapshot policy is a low-maintenance starting point. The
laptop's local backup timer and reporting have no network dependency.
[TrueNAS periodic snapshots](https://www.truenas.com/docs/scale/dataprotection/periodicsnapshottasks/addingperiodicsnapshottasks/)

## Deadline data contract

The local schedule's reporting projection lives in `battery_store.deadline_context`.
Dates resolve in the local IANA zone. An ambiguous time uses the first
occurrence and a nonexistent time advances to the first valid minute.
The projection returns the active and next hard deadline, with UTC epoch
seconds for `start`, `ready`, `end`, `created_at` and `expires_at`.
It also carries `source` and `confidence` from 0 to 1. A recurring local
rule has no individual creation timestamp. Its observation is in the
policy-event history.

A future local deadline provider can return the same fields with a source label
and expiry. It should omit upstream personal data and must tolerate being
unavailable. Temporary overrides and explicit deadlines have priority.
Policy events should record the selected deadline and reason when a provider
changes it. The existing recurring local schedule supplies the offline fallback.
