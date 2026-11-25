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
  current limits when present. Their product is the driver-reported source
  limit. A load draw, charger nameplate wattage and negotiated source limit
  are distinct measurements. Generic AC without an online UCSI source is
  `mains_unidentified`.
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
and changes in charging policy break continuity. A gap never inherits the
preceding SOC, temperature or state. The JSON report includes per-metric
coverage, unknown duration, and the largest gaps. A zero measured total
requires checking its coverage.

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
The CPU threshold for a heavy workload is 70% across the sample interval.
Deadline reports distinguish observed success, estimated misses, an observed
80% override and unknown outcomes. Headroom is measured from the first
observed full reading to the deadline. Check the unknown count alongside any
success rate.

Compare historical and current intervals with similar starting SOC, AC context,
workload, time of day and coverage wherever those fields are available. The
early UPower baseline supports estimates of SOC exposure for a portion of the
day. It cannot establish a change in degradation or supply enough comparable
adapter-specific charging curves. A future adaptive policy needs repeated full
charges and conservative completion bounds for each adapter and workload,
including the taper from 98% to Full. Lower starting SOC and limited or unknown
adapter power need a larger margin. Current deadlines remain locally configured
and the effective target continues to come from the charge controller.

## Local retention and recovery

The versioned database lives in `/var/lib/dot-charge/telemetry/battery.sqlite3`.
Root writes it. The laptop owner's primary group can read it. The raw history
is retained for the lifetime of the database. The daily timer uses the SQLite
backup API, checks the snapshot with `quick_check`, verifies a compressed
round trip, and keeps seven daily and four weekly copies under `backups/`.
Wake alarms and network transfers are unnecessary. The snapshots share the
laptop's disk failure risk. [SQLite Online Backup API](https://www.sqlite.org/backup.html)

To check a backup, decompress it to a private temporary file and run
`PRAGMA integrity_check` with SQLite. For a deliberate restore, stop the
collector, preserve the live database, and install the verified file at the
same path with owner `root`, the laptop owner's group, and mode `0640`.
Restart the collector and check `dot-charge history`. Review data and backup
sizes after roughly 30 days of normal use to size secondary telemetry
retention using observed growth.

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
