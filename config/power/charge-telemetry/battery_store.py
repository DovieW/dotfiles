"""Storage, clock and deadline conventions shared by battery telemetry commands."""

import datetime as dt
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BASE = Path('/var/lib/dot-charge/telemetry')
DATABASE = BASE / 'battery.sqlite3'
CONTROLLER = Path('/usr/local/bin/dot-charge')
SOCKET = BASE / 'notify.sock'
VERSION = 1


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def number(value, scale=1):
    try:
        result = float(value) / scale
    except (ValueError, TypeError):
        return None
    return result if abs(result) < float('inf') else None


def local_zone():
    local = Path('/etc/localtime').resolve()
    try:
        key = str(local.relative_to('/usr/share/zoneinfo'))
        return key, ZoneInfo(key)
    except (ValueError, ZoneInfoNotFoundError):
        return 'system local time', dt.datetime.now().astimezone().tzinfo


def utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).isoformat(timespec='milliseconds')


def wall_time(day, value, zone):
    """Resolve a local time, using the first fold and advancing over a DST gap."""
    wall = dt.datetime.combine(day, dt.time.fromisoformat(value))
    if wall.replace(tzinfo=zone).utcoffset() == wall.replace(tzinfo=zone, fold=1).utcoffset():
        return wall.replace(tzinfo=zone).timestamp()
    for minute in range(181):
        candidate = wall + dt.timedelta(minutes=minute)
        instant = candidate.replace(tzinfo=zone).timestamp()
        if dt.datetime.fromtimestamp(instant, zone).replace(tzinfo=None) == candidate:
            return instant
    raise ValueError(f'Could not resolve local time {wall}')


def deadline_context(ts, zone, windows):
    """Project local hard deadlines for reporting, independent of firmware control."""
    day = dt.datetime.fromtimestamp(ts, zone).date()
    occurrences = []
    for offset in range(-1, 8):
        date = day + dt.timedelta(days=offset)
        for window in windows:
            if date.weekday() in window['days']:
                occurrences.append({
                    'start': wall_time(date, window['start'], zone),
                    'ready': wall_time(date, window['ready'], zone),
                    'end': wall_time(date, window['end'], zone),
                    'source': 'local_schedule', 'confidence': 1.0,
                    'created_at': None, 'expires_at': wall_time(date, window['end'], zone),
                })
    active = next((d for d in occurrences if d['start'] <= ts < d['end']), None)
    upcoming = min((d for d in occurrences if d['ready'] >= ts),
                   key=lambda d: d['ready'], default=None)
    return active, upcoming


def clocks():
    stamp = time.time()
    name, zone = local_zone()
    mono = time.clock_gettime(time.CLOCK_MONOTONIC)
    return {
        'timestamp': stamp, 'timezone': name,
        'utc_offset_s': dt.datetime.fromtimestamp(stamp, zone).utcoffset().total_seconds(),
        'boot_id': read(Path('/proc/sys/kernel/random/boot_id')),
        'monotonic_s': mono, 'boottime_s': time.clock_gettime(time.CLOCK_BOOTTIME),
    }


@contextmanager
def connect(path=DATABASE, writable=False):
    uri = path.resolve().as_uri() + ('?mode=rwc' if writable else '?mode=ro')
    db = sqlite3.connect(uri, uri=True, timeout=0.5 if writable else 2)
    try:
        with db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version == 0 and writable:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS records (
                        timestamp REAL NOT NULL,
                        source TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        PRIMARY KEY (timestamp, source, kind)
                    ) WITHOUT ROWID;
                    CREATE INDEX IF NOT EXISTS records_kind ON records (kind, timestamp);
                    PRAGMA user_version = 1;
                    COMMIT;
                """)
            elif version != VERSION:
                raise ValueError(f'Unsupported battery database version {version}')
            yield db
    finally:
        db.close()


def append(db, records):
    db.executemany('INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?)', (
        (data['timestamp'], source, kind,
         json.dumps({k: v for k, v in data.items() if k != 'timestamp' and v is not None},
                    separators=(',', ':'), allow_nan=False))
        for source, kind, data in records
    ))


def records(db, start, end):
    return [
        dict(json.loads(payload), timestamp=ts, source=source, kind=kind)
        for ts, source, kind, payload in db.execute(
            'SELECT * FROM records WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp, source, kind',
            (start, end))
    ]


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
