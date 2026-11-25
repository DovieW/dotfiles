"""Read supported battery interfaces. Every sysfs and D-Bus operation is read-only."""

from contextlib import closing
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

from battery_store import (BASE, CONTROLLER, DATABASE, SOCKET, append, clocks, connect,
                           deadline_context, local_zone, number, read, sync_directory)

POWER = Path('/sys/class/power_supply')
UP_HISTORY = Path('/var/lib/upower')
HWMON = Path('/sys/class/hwmon')
DRM = Path('/sys/class/drm')
PROFILE = 'org.freedesktop.UPower.PowerProfiles'
PROFILE_PATH = '/org/freedesktop/UPower/PowerProfiles'
PROPERTIES = 'org.freedesktop.DBus.Properties'
BATTERY_IFACE = 'org.freedesktop.UPower.Device'
UP_STATES = {'charging': 'Charging', 'discharging': 'Discharging',
             'fully-charged': 'Full', 'pending-charge': 'Not charging',
             'pending-discharge': 'Not charging'}
CONTROLLER_EVENTS = {'firmware_change', 'hold', 'auto', 'set-window'}


def bus_value(bus, name, path, iface, key):
    from gi.repository import Gio, GLib

    try:
        return bus.call_sync(name, path, PROPERTIES, 'Get', GLib.Variant('(ss)', (iface, key)),
                             None, Gio.DBusCallFlags.NO_AUTO_START, 200, None).unpack()[0]
    except GLib.Error:
        return None


def mode(battery):
    raw = read(battery / 'charge_types') or ''
    selected = re.search(r'\[([^]]+)\]', raw)
    if selected:
        return selected[1]
    return raw if raw in ('Standard', 'Fast', 'Long_Life') else None


def battery_fields(battery):
    # This single kernel event snapshot keeps most gauge readings close in time.
    items = dict(line.split('=', 1) for line in (read(battery / 'uevent') or '').splitlines() if '=' in line)

    def value(key, scale=1):
        return number(items.get(f'POWER_SUPPLY_{key}'), scale)

    soc = value('CAPACITY')
    state = items.get('POWER_SUPPLY_STATUS')
    sign = {'Charging': 1, 'Discharging': -1}.get(state)
    voltage = value('VOLTAGE_NOW', 1e6)
    current = value('CURRENT_NOW', 1e6)
    power = value('POWER_NOW', 1e6)
    signed = 0.0 if power == 0 else sign * abs(power) if sign is not None and power is not None else None
    signed_current = sign * abs(current) if sign is not None and current is not None else None
    source = 'sysfs_power_now' if signed is not None else None
    if signed is None and signed_current is not None and voltage:
        signed = signed_current * voltage
        source = 'sysfs_current_x_voltage'
    if signed is not None and signed_current is None and voltage:
        signed_current = signed / voltage
        current_source = 'derived_power_over_voltage'
    else:
        current_source = 'sysfs_current_now' if signed_current is not None else None
    full = value('ENERGY_FULL', 1e6)
    design = value('ENERGY_FULL_DESIGN', 1e6)
    level = items.get('POWER_SUPPLY_CAPACITY_LEVEL')
    temp = value('TEMP', 10)
    temp_source = 'sysfs_battery_temp' if temp is not None else None
    if temp is None:
        for sensor in sorted(battery.glob('hwmon*/temp1_input')):
            temp = number(read(sensor), 1e3)
            if temp is not None:
                temp_source = 'battery_hwmon_temp1'
                break
    return {
        'battery_model': items.get('POWER_SUPPLY_MODEL_NAME'),
        'battery_present': value('PRESENT'), 'soc_pct': soc,
        'full_wh': full, 'design_wh': design, 'stored_wh': value('ENERGY_NOW', 1e6),
        'health_pct': 100 * full / design if full is not None and design else None,
        'battery_v': voltage, 'battery_temp_c': temp, 'battery_temp_source': temp_source,
        'battery_power_w': signed, 'battery_power_source': source,
        'battery_current_a': signed_current, 'battery_current_source': current_source,
        'firmware_cycles': value('CYCLE_COUNT'), 'battery_status': state, 'capacity_level': level,
        'genuinely_full': soc == 100 and (state == 'Full' or (level == 'Full' and state == 'Not charging'))
        if soc is not None else None,
        'firmware_mode': mode(battery),
        'start_threshold_pct': number(read(battery / 'charge_control_start_threshold')),
        'end_threshold_pct': number(read(battery / 'charge_control_end_threshold')),
    }


def adapter(root):
    mains = []
    usb = []
    for path in sorted(root.glob('*')):
        supply = read(path / 'type')
        if supply == 'Mains':
            online = read(path / 'online')
            if online is not None:
                mains.append(online == '1')
        elif supply and supply.startswith('USB') and read(path / 'online') == '1':
            usb_type = read(path / 'usb_type') or ''
            selected = re.search(r'\[([^]]+)\]', usb_type)
            volts = number(read(path / 'voltage_max'), 1e6)
            amps = number(read(path / 'current_max'), 1e6)
            usb.append({
                'port': path.name, 'type': selected[1] if selected else supply,
                'voltage_max_v': volts, 'current_max_a': amps,
                'source_limit_w': volts * amps if volts and amps else None,
                'voltage_now_v': number(read(path / 'voltage_now'), 1e6),
                'current_now_a': number(read(path / 'current_now'), 1e6),
            })
    return {
        'ac_online': bool(usb) or any(mains) if usb or mains else None,
        'mains_online': any(mains) if mains else None,
        'adapter_class': 'usb_c' if usb else ('mains_unidentified' if any(mains) else None),
        'usb_sources': usb or None,
    }


def cpu_fields():
    stat = read(Path('/proc/stat'))
    fields = list(map(int, stat.splitlines()[0].split()[1:9])) if stat else []
    temps = []
    for path in HWMON.glob('*'):
        if read(path / 'name') in ('coretemp', 'k10temp', 'zenpower'):
            for sensor in path.glob('temp*_input'):
                temp = number(read(sensor), 1e3)
                if temp is not None:
                    temps.append(temp)
    return {
        'cpu_total_ticks': sum(fields) if len(fields) == 8 else None,
        'cpu_busy_ticks': sum(fields) - fields[3] - fields[4] if len(fields) == 8 else None,
        'cpu_max_temp_c': max(temps, default=None),
    }


def gpu_runtime(drm=DRM):
    # The runtime PM status is cached in the kernel. Opening DRM or reading
    # driver-backed GPU sensor attributes could otherwise resume the GPU.
    return {card.name: read(card / 'device/power/runtime_status') for card in drm.glob('card[0-9]*')
            if card.name[4:].isdigit()} or None


class Collector:
    def __init__(self):
        self.controller = runpy.run_path(str(CONTROLLER))

    def sample(self, bus=None):
        data = clocks()
        battery = POWER / 'BAT0'
        # Read AC on both sides of the gauge snapshot to flag conflicting samples.
        before = adapter(POWER)
        data.update(battery_fields(battery))
        after = adapter(POWER)
        data.update(after)
        if adapter_state(before) != adapter_state(after):
            data.update(ac_online=None, adapter_class=None, power_transition=True)
        data.update(cpu_fields())
        data.update(period_s=60 if data.get('battery_status') == 'Charging' else 300)
        data['power_profile'] = bus_value(bus, PROFILE, PROFILE_PATH, PROFILE, 'ActiveProfile') if bus else None
        if bus and data['battery_temp_c'] is None:
            temp = bus_value(bus, 'org.freedesktop.UPower', '/org/freedesktop/UPower/devices/battery_BAT0',
                             BATTERY_IFACE, 'Temperature')
            if temp and -30 <= temp <= 90:
                data.update(battery_temp_c=temp, battery_temp_source='upower_temperature')
        # Unsupported sensors are absent in storage and null in the JSON/CSV view.
        data.update(battery_resistance_ohm=None, gpu_load_pct=None, gpu_temp_c=None,
                    gpu_runtime_status=gpu_runtime())
        try:
            now = dt.datetime.fromtimestamp(data['timestamp'])
            windows = self.controller['read_windows']()
            override = self.controller['current_override'](now)
            if override:
                target, change, reason = override['percent'], override['until'], 'override expires'
            else:
                target, change = self.controller['schedule'](now, windows)
                reason = 'schedule changes'
            _, zone = local_zone()
            active, upcoming = deadline_context(data['timestamp'], zone, windows)
            data.update(requested_pct=target, policy_reason=reason, policy_next_ts=change, override=override,
                        active_deadline=active, next_deadline=upcoming)
            return data, windows
        except (OSError, ValueError, KeyError, TypeError) as exc:
            data['policy_error'] = str(exc)
            return data, None


def event(name, detail=None):
    try:
        with connect(writable=True) as db:
            append(db, [('local', name, dict(clocks(), detail=detail))])
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f'Battery telemetry event {name}: {exc}', file=sys.stderr)


def sleep_sample(phase, operation):
    # The frozen user session and the power path do not depend on D-Bus or this hook.
    try:
        data, _ = Collector().sample()
        with connect(writable=True) as db:
            append(db, [('local', phase, dict(data, detail=operation))])
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f'Battery telemetry {phase}: {exc}', file=sys.stderr)


def adapter_state(data):
    ports = tuple((port['port'], port['type'], port['source_limit_w']) for port in data.get('usb_sources') or [])
    return data.get('ac_online'), data.get('mains_online'), data.get('adapter_class'), ports


def power_key(data):
    return (adapter_state(data), data.get('battery_status'),
            data.get('firmware_mode'), data.get('power_profile'))


def watch():
    from gi.repository import Gio, GLib
    import pyudev

    collector = Collector()
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    loop = GLib.MainLoop()
    monitor = pyudev.Monitor.from_netlink(pyudev.Context())
    monitor.filter_by(subsystem='power_supply')
    monitor.start()
    SOCKET.unlink(missing_ok=True)
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(SOCKET))
    SOCKET.chmod(0o600)
    receiver.setblocking(False)
    timer = None
    pending = set()
    pending_id = None
    previous = None
    policy_snapshot = None
    last_battery_notice = None
    source_notices = {}

    def capture(force=False, trigger=None):
        nonlocal previous, timer, policy_snapshot
        try:
            data, windows = collector.sample(bus)
            state = (data.get('requested_pct'), data.get('policy_reason'), data.get('override'),
                     data.get('timezone'), windows)
            changed = state != policy_snapshot
            if force or previous is None or power_key(data) != power_key(previous) or changed:
                queued = [('local', 'sample', dict(data, trigger=trigger or 'periodic'))]
                if changed:
                    queued.append(('local', 'policy', dict(data, windows=windows, trigger=trigger)))
                with connect(writable=True) as db:
                    append(db, queued)
                previous, policy_snapshot = data, state
                if timer is not None:
                    GLib.source_remove(timer)
                    timer = None
        except (OSError, ValueError, sqlite3.Error) as exc:
            print(f'Battery telemetry sample: {exc}', file=sys.stderr)
        if timer is None:
            timer = GLib.timeout_add_seconds(previous['period_s'] if previous else 60, periodic)

    def periodic():
        nonlocal timer
        timer = None
        capture(True)
        return False

    def flush_power():
        nonlocal pending_id
        pending_id = None
        trigger = ','.join(sorted(pending))
        pending.clear()
        capture(trigger=trigger)
        return False

    def queue_power(trigger):
        nonlocal pending_id
        pending.add(trigger)
        if pending_id is None:
            pending_id = GLib.timeout_add(500, flush_power)

    def udev_ready(*_):
        nonlocal last_battery_notice
        for _ in range(64):
            device = monitor.poll(timeout=0)
            if device is None:
                break
            if device.sys_name == 'BAT0':
                keys = ('PRESENT', 'STATUS', 'CHARGE_TYPES')
                notice = tuple(device.properties.get(f'POWER_SUPPLY_{key}') for key in keys)
                if notice != last_battery_notice:
                    last_battery_notice = notice
                    queue_power('battery_state')
            elif device.sys_name == 'ADP0' or device.sys_name.startswith('ucsi-source-psy-'):
                online = device.properties.get('POWER_SUPPLY_ONLINE')
                if online != source_notices.get(device.sys_name):
                    source_notices[device.sys_name] = online
                    event('power_source', {'port': device.sys_name, 'online': online})
                queue_power('power_source')
        return True

    def controller_ready(*_):
        for _ in range(64):
            try:
                message = json.loads(receiver.recv(2048))
                kind = message.pop('kind')
                if kind in CONTROLLER_EVENTS:
                    event(kind, message)
                    capture(True, kind)
            except BlockingIOError:
                break
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
        return True

    def profile_changed(_connection, _sender, _path, _iface, _signal, params):
        iface, changes, invalidated = params.unpack()
        if iface == PROFILE and ('ActiveProfile' in changes or 'ActiveProfile' in invalidated):
            queue_power('power_profile')

    def config_changed(_monitor, file, other_file, _kind):
        if any(path is not None and path.get_basename() in
               ('override.json', 'schedule.json', 'charge-schedule.json') for path in (file, other_file)):
            queue_power('policy_file')

    def stopping(_connection, _sender, _path, _iface, _signal, params):
        active, details = params.unpack()
        if active:
            event('shutdown_requested', details.get('type'))
            capture(True, 'shutdown_requested')
        else:
            event('shutdown_cancelled')

    def stop():
        # PID 1 also stops this service on ordinary administrative restarts.
        event('collector_stop')
        loop.quit()
        return False

    GLib.io_add_watch(monitor.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, udev_ready)
    GLib.io_add_watch(receiver.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, controller_ready)
    bus.signal_subscribe(PROFILE, PROPERTIES, 'PropertiesChanged', PROFILE_PATH,
                         None, Gio.DBusSignalFlags.NONE, profile_changed)
    bus.signal_subscribe('org.freedesktop.login1', 'org.freedesktop.login1.Manager',
                         'PrepareForShutdownWithMetadata', '/org/freedesktop/login1', None,
                         Gio.DBusSignalFlags.NONE, stopping)
    config_monitors = [
        Gio.File.new_for_path(str(path)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        for path in (BASE.parent, Path('/etc/dotfiles'))
    ]
    for config_monitor in config_monitors:
        config_monitor.connect('changed', config_changed)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, stop)
    now = clocks()
    with connect(writable=True) as db:
        last = db.execute("SELECT payload FROM records WHERE kind='boot' AND source='local' "
                          "ORDER BY timestamp DESC LIMIT 1").fetchone()
        if last is None or json.loads(last[0]).get('boot_id') != now['boot_id']:
            append(db, [('local', 'boot', now)])
    event('collector_start')
    capture(True, 'collector_start')
    try:
        loop.run()
    finally:
        receiver.close()
        SOCKET.unlink(missing_ok=True)


UP_FIELDS = {
    'charge': ('soc_pct', 'pct'), 'rate': ('upower_rate_w', 'W'),
    'voltage': ('battery_v', 'V'), 'time-full': ('upower_to_full_s', 's'),
    'time-empty': ('upower_to_empty_s', 's'),
}


def historical_rows(paths):
    for series, path in paths.items():
        field, unit = UP_FIELDS[series]
        if not path.exists():
            continue
        seen = {}
        conflicts = {}
        for line in path.read_text(errors='replace').splitlines():
            words = line.split()
            if len(words) != 3 or not words[0].isdecimal():
                continue
            stamp = int(words[0])
            value = number(words[1])
            if value is None or stamp == 0:
                continue
            if stamp in seen:
                if words[1:] != seen[stamp]:
                    others = conflicts.setdefault(stamp, [seen[stamp]])
                    if words[1:] not in others:
                        others.append(words[1:])
                continue
            seen[stamp] = words[1:]
            state = UP_STATES.get(words[2])
            yield f'upower_{series}', 'sample', dict(
                timestamp=stamp, **{field: value}, battery_status=state, history_unit=unit,
                genuinely_full=value == 100 and state == 'Full' if series == 'charge' else None,
                battery_power_w=value * (1 if state == 'Charging' else -1)
                if series == 'rate' and state in ('Charging', 'Discharging') else None,
                battery_power_source='upower_history_rate' if series == 'rate' else None,
            )
        for stamp, values in conflicts.items():
            yield f'upower_{series}', 'legacy_conflict', dict(
                timestamp=stamp, detail=values, history_unit=unit)


def journal_boundaries(start):
    query = subprocess.run(
        ['/usr/bin/journalctl', '_TRANSPORT=kernel', '--no-pager', '--quiet', '--all',
         f'--since=@{int(start)}', '--grep=^PM: suspend (entry|exit)', '-o', 'json',
         '--output-fields=MESSAGE,_BOOT_ID'],
        text=True, capture_output=True, timeout=30, check=False,
    )
    for line in query.stdout.splitlines():
        record = json.loads(line)
        message = record.get('MESSAGE')
        if isinstance(message, str):
            phase = 'suspend' if message.startswith('PM: suspend entry') else 'resume'
            yield 'kernel_journal', phase, {
                'timestamp': int(record['__REALTIME_TIMESTAMP']) / 1e6, 'boot_id': record.get('_BOOT_ID'),
            }
    boots = subprocess.run(
        ['/usr/bin/journalctl', '--list-boots', '--no-pager', '-o', 'json'],
        text=True, capture_output=True, timeout=10, check=False,
    )
    if boots.returncode == 0 and boots.stdout.strip():
        for boot in json.loads(boots.stdout):
            yield 'kernel_journal', 'boot', {
                'timestamp': int(boot['first_entry']) / 1e6, 'boot_id': boot['boot_id'],
            }


def import_history():
    # UPower names the internal battery history using the model, design Wh and serial.
    battery = POWER / 'BAT0'
    model = read(battery / 'model_name')
    design = number(read(battery / 'energy_full_design'), 1e6)
    serial = read(battery / 'serial_number')
    if not (model and design and serial and '/' not in model and '/' not in serial):
        print('No matching internal UPower history identity')
        return
    identity = f'{model}-{int(design)}-{serial}'
    paths = {series: UP_HISTORY / f'history-{series}-{identity}.dat' for series in UP_FIELDS}
    legacy = list(historical_rows(paths))
    if not legacy:
        print('No matching UPower history files yet')
        return
    start = min(row['timestamp'] for _, _, row in legacy)
    boundaries = list(journal_boundaries(start))
    with connect(writable=True) as db:
        first = db.execute("SELECT MIN(timestamp) FROM records WHERE source='local' AND kind='sample'").fetchone()[0]
        append(db, ((source, kind, data) for source, kind, data in legacy + boundaries
                    if start <= data['timestamp'] and (first is None or data['timestamp'] < first)))
    (BASE / 'history-imported').touch()
    print(f'Read {len(legacy)} historical UPower measurements')


def backup():
    backups = BASE / 'backups'
    backups.mkdir(mode=0o2750, exist_ok=True)
    today = dt.datetime.now().date()
    daily = backups / f'daily-{today.isoformat()}.sqlite3.gz'
    week = today - dt.timedelta(days=today.weekday())
    weekly = backups / f'weekly-{week.isoformat()}.sqlite3.gz'
    with tempfile.TemporaryDirectory(dir=backups) as directory:
        snapshot = Path(directory) / 'snapshot.sqlite3'
        packed = Path(directory) / 'snapshot.sqlite3.gz'
        with connect() as db, closing(sqlite3.connect(snapshot)) as dest:
            db.backup(dest, pages=128, sleep=0.025)
            if dest.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('Battery backup failed SQLite quick_check')
        with snapshot.open('rb') as src, packed.open('wb') as raw:
            with gzip.GzipFile(fileobj=raw, filename='', mode='wb', compresslevel=3) as output:
                shutil.copyfileobj(src, output)
            raw.flush()
            os.fsync(raw.fileno())
        with gzip.open(packed, 'rb') as src, snapshot.open('rb') as verified:
            while chunk := verified.read(1 << 20):
                if src.read(len(chunk)) != chunk:
                    raise ValueError('Battery backup failed compressed round-trip verification')
            if src.read(1):
                raise ValueError('Battery backup has unexpected trailing data')
        packed.replace(daily)
        if not weekly.exists():
            os.link(daily, weekly)
    for prefix, keep in (('daily', 7), ('weekly', 4)):
        for old in sorted(backups.glob(f'{prefix}-????-??-??.sqlite3.gz'), reverse=True)[keep:]:
            old.unlink()
    sync_directory(backups)
    print(f'Verified SQLite snapshot {daily.name}')
