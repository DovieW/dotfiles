"""Time and energy estimates from adjacent compatible battery observations."""

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import math
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from battery_analysis import (WAKE_TOLERANCE_S, conservation_episodes, deadline_cause, describe_sleep, gap_bounds,
                              gap_model, sleep_pairs, timing_summary, usb_signature, wake_evidence)
from battery_store import utc, wall_time

SOC_LEVELS = (80, 90, 95, 98)
TEMP_LEVELS = (30, 35, 40)
CHARGE_LEVELS = (90, 95, 98, 100)
BOUNDARIES = {'boot', 'suspend', 'resume', 'collector_stop', 'collector_start', 'power_source'}
HEAVY_CPU_PCT = 70
HIGH_VOLTAGE_V = (16.8, 17.0, 17.2)


def compatible(left, right, cuts, allow_full_transition=False):
    a, b = left['timestamp'], right['timestamp']
    if left['source'] != right['source'] or b <= a:
        return False
    if left['kind'] == 'suspend' or right['kind'] == 'resume':
        return False
    if bisect_right(cuts, a) < bisect_left(cuts, b):
        return False
    if left['source'].startswith('upower_'):
        return (b - a <= 300 and left.get('battery_status') is not None
                and (left.get('battery_status') == right.get('battery_status')
                     or (allow_full_transition and right.get('genuinely_full'))))
    if (not left.get('boot_id') or left.get('boot_id') != right.get('boot_id')
            or left.get('power_transition') or right.get('power_transition')):
        return False
    if b - a > 2 * min(left['period_s'], right['period_s']):
        return False
    boot_delta = right['boottime_s'] - left['boottime_s']
    awake_delta = right['monotonic_s'] - left['monotonic_s']
    if abs(boot_delta - awake_delta) > 0.05 or abs(boot_delta - (b - a)) > 2:
        return False
    signature = ('ac_online', 'adapter_class', 'mains_online', 'firmware_mode', 'requested_pct', 'override')
    return all(left.get(key) == right.get(key) for key in signature) and usb_signature(left) == usb_signature(right)


def adapter_key(row):
    ports = [
        f"{port['port']}:{port.get('type')}:{port.get('source_limit_w')}"
        + (f":{port['partner_vid']}:{port.get('partner_pid')}" if port.get('partner_vid') else '')
        + (f":{port.get('current_now_a')}A" if port.get('type') == 'PD' and not port.get('source_limit_w')
           and port.get('current_now_a') else '')
        for port in row.get('usb_sources', [])
    ]
    return '/'.join(ports) or row.get('adapter_class') or 'unknown'


def cpu_load(left, right):
    if any(row.get(key) is None for row in (left, right)
           for key in ('cpu_total_ticks', 'cpu_busy_ticks')):
        return None
    total = right['cpu_total_ticks'] - left['cpu_total_ticks']
    busy = right['cpu_busy_ticks'] - left['cpu_busy_ticks']
    return 100 * busy / total if 0 <= busy <= total and total > 0 else None


def lerp(values, ratio):
    return values[0] + ratio * (values[1] - values[0])


def pair(a, b, key):
    values = a.get(key), b.get(key)
    return values if all(value is not None for value in values) else None


def split_exposure(soc, temp, start_ratio, end_ratio):
    # Split at every bucket crossing. Midpoints then belong to exactly one bucket.
    cuts = {start_ratio, end_ratio}
    for pair_values, levels in ((soc, (10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 100)),
                                (temp, TEMP_LEVELS)):
        if pair_values and pair_values[1] != pair_values[0]:
            for level in levels:
                ratio = (level - pair_values[0]) / (pair_values[1] - pair_values[0])
                if start_ratio < ratio < end_ratio:
                    cuts.add(ratio)
    cuts = sorted(cuts)
    for start, end in zip(cuts, cuts[1:]):
        midpoint = (start + end) / 2
        yield end - start, lerp(soc, midpoint) if soc else None, lerp(temp, midpoint) if temp else None


def soc_bucket(soc):
    return f'{min(90, max(0, int(soc / 10) * 10)):02d}'


def temp_bucket(temp):
    return str(max((threshold for threshold in TEMP_LEVELS if temp >= threshold), default='<30'))


def workload_percent(cpu, gpu=None):
    return max(value for value in (cpu, gpu) if value is not None) if cpu is not None or gpu is not None else None


def voltage_exposure(group, voltage, ac, low, high, span):
    group['estimated_seconds']['battery_voltage'] += (high - low) * span
    if ac is not None:
        group['estimated_seconds']['battery_voltage_ac_context'] += (high - low) * span
    edges = set(HIGH_VOLTAGE_V)
    edges.update(bin_index / 4 for bin_index in range(math.floor(min(voltage) * 4) + 1,
                                                       math.ceil(max(voltage) * 4)))
    cuts = {low, high}
    if voltage[0] != voltage[1]:
        cuts.update(ratio for edge in edges
                    if low < (ratio := (edge - voltage[0]) / (voltage[1] - voltage[0])) < high)
    points = sorted(cuts)
    for first, last in zip(points, points[1:]):
        value = lerp(voltage, (first + last) / 2)
        seconds = (last - first) * span
        group['battery_voltage_bucket_seconds'][f'{math.floor(value * 4) / 4:.2f}'] += seconds
        if ac is True:
            for threshold in HIGH_VOLTAGE_V:
                if value > threshold:
                    group['battery_voltage_above_on_ac_seconds'][str(threshold)] += seconds


def add_interval(group, left, right, start, end):
    a, b = left['timestamp'], right['timestamp']
    span = b - a
    low, high = (start - a) / span, (end - a) / span
    estimates = group['estimated_seconds']
    soc = pair(left, right, 'soc_pct')
    temp = pair(left, right, 'battery_temp_c')
    if left.get('battery_temp_source') != right.get('battery_temp_source'):
        temp = None
    if soc:
        estimates['soc'] += end - start
    if temp:
        estimates['battery_temp'] += end - start
    ac = left.get('ac_online')
    voltage = pair(left, right, 'battery_v')
    if voltage and 0 < min(voltage) <= max(voltage) < 100:
        voltage_exposure(group, voltage, ac, low, high, span)
    cpu = workload_percent(cpu_load(left, right), right.get('gpu_load_pct'))
    if soc and ac is not None:
        estimates['soc_ac_context'] += end - start
    if soc and cpu is not None:
        estimates['soc_workload_context'] += end - start
    if soc and temp:
        estimates['soc_temperature_joint'] += end - start
    if soc and left.get('firmware_mode') is not None:
        estimates['soc_firmware_mode'] += end - start
    for fraction, percent, temperature in split_exposure(soc, temp, low, high):
        seconds = span * fraction
        if temperature is not None:
            for level in TEMP_LEVELS:
                if temperature > level:
                    group['battery_temp_above_seconds'][str(level)] += seconds
        if percent is None:
            continue
        estimates['soc_pct_seconds'] += percent * seconds
        bucket = soc_bucket(percent)
        group['soc_bucket_seconds'][bucket] += seconds
        if temperature is not None:
            group['soc_temperature_seconds'][f'{bucket}/{temp_bucket(temperature)}'] += seconds
        for level in SOC_LEVELS:
            if percent > level:
                key = str(level)
                group['soc_above_seconds'][key] += seconds
                if ac is not None:
                    group['soc_above_seconds_on_ac' if ac else 'soc_above_seconds_on_battery'][key] += seconds
                if cpu is not None and cpu >= HEAVY_CPU_PCT:
                    group['soc_above_seconds_heavy_workload'][key] += seconds
        if soc == (100, 100):
            group['soc_at_100_seconds'] += seconds
        for level in (10, 20):
            if percent < level:
                group['soc_below_seconds'][str(level)] += seconds
        if percent > 80 and left.get('firmware_mode') == 'Long_Life':
            group['above_80_conservation_seconds'] += seconds

    power = pair(left, right, 'battery_power_w')
    if power is None or left.get('battery_power_source') != right.get('battery_power_source'):
        return
    # The change from charging to discharging has unknown timing. Count neither side across it.
    if power[0] * power[1] < 0 or left.get('battery_status') != right.get('battery_status'):
        return
    estimates['battery_power'] += end - start
    if ac is not None:
        estimates['battery_power_ac_context'] += end - start
    if ac is True:
        group['ac_power_coverage_by_adapter_seconds'][adapter_key(left)] += end - start
    wh = (lerp(power, low) + lerp(power, high)) / 2 * (end - start) / 3600
    if wh >= 0:
        group['charged_wh'] += wh
    else:
        group['discharged_wh'] -= wh
        if ac is True:
            group['discharged_on_ac_wh'] -= wh
            group['discharged_on_ac_by_adapter_wh'][adapter_key(left)] -= wh
            group['discharged_on_ac_seconds'] += end - start
        design = pair(left, right, 'design_wh')
        if design and design[0] == design[1] and design[0] > 0:
            group['equivalent_full_cycles'] -= wh / design[0]
            group['efc_covered_discharge_wh'] -= wh


def groups_for(start, end, group_by, zone):
    cursor = start
    while cursor < end:
        day = dt.datetime.fromtimestamp(cursor, zone).date()
        if group_by == 'daily':
            name = day.isoformat()
            next_day = day + dt.timedelta(days=1)
        elif group_by == 'weekly':
            monday = day - dt.timedelta(days=day.weekday())
            name = monday.isoformat()
            next_day = monday + dt.timedelta(days=7)
        elif group_by == 'monthly':
            name = day.strftime('%Y-%m')
            next_day = (day.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        else:
            yield 'lifetime', cursor, end
            return
        boundary = min(end, wall_time(next_day, '00:00', zone))
        yield name, cursor, boundary
        cursor = boundary


def new_group(start, end):
    result = {
        'from_utc': utc(start), 'to_utc': utc(end), 'elapsed_seconds': end - start,
        'observations': Counter(), 'estimated_seconds': Counter(),
        'soc_at_100_seconds': 0.0, 'above_80_conservation_seconds': 0.0,
        'charged_wh': 0.0, 'discharged_wh': 0.0, 'discharged_on_ac_wh': 0.0,
        'discharged_on_ac_seconds': 0.0, 'efc_covered_discharge_wh': 0.0,
        'equivalent_full_cycles': 0.0, 'capacity_and_firmware_cycles': None,
        'charging_sessions': [], 'charging_deadlines': [],
    }
    for field, levels in (
        ('soc_bucket_seconds', (f'{value:02d}' for value in range(0, 100, 10))),
        ('soc_above_seconds', SOC_LEVELS), ('soc_above_seconds_on_ac', SOC_LEVELS),
        ('soc_above_seconds_on_battery', SOC_LEVELS), ('soc_above_seconds_heavy_workload', SOC_LEVELS),
        ('soc_below_seconds', (10, 20)), ('battery_temp_above_seconds', TEMP_LEVELS),
        ('soc_temperature_seconds', ()), ('discharged_on_ac_by_adapter_wh', ()),
        ('battery_voltage_bucket_seconds', ()), ('ac_power_coverage_by_adapter_seconds', ()),
        ('battery_voltage_above_on_ac_seconds', HIGH_VOLTAGE_V),
    ):
        result[field] = Counter({str(level): 0.0 for level in levels})
    return result


def merged_ranges(ranges):
    joined = []
    for start, end in sorted(ranges):
        if joined and start <= joined[-1][1]:
            joined[-1][1] = max(end, joined[-1][1])
        else:
            joined.append([start, end])
    return joined


def unknown_ranges(start, end, ranges):
    cursor = start
    for first, last in merged_ranges(ranges):
        if first > cursor:
            yield cursor, first
        cursor = max(cursor, last)
    if cursor < end:
        yield cursor, end


def slope(points):
    if len(points) < 3:
        return None
    x_avg = sum(x for x, _ in points) / len(points)
    y_avg = sum(y for _, y in points) / len(points)
    variance = sum((x - x_avg) ** 2 for x, _ in points)
    if variance <= 0:
        return None
    return sum((x - x_avg) * (y - y_avg) for x, y in points) / variance


def capacity_summary(samples, energy, zone):
    if not samples:
        return None
    daily = defaultdict(list)
    health = defaultdict(list)
    for row in samples:
        if row.get('full_wh') is not None:
            day = dt.datetime.fromtimestamp(row['timestamp'], zone).date()
            daily[day].append(row['full_wh'])
            if row.get('health_pct') is not None:
                health[day].append(row['health_pct'])
    series = [(day, median(values)) for day, values in daily.items()]
    first, last = samples[0], samples[-1]
    cycle_values = [row['firmware_cycles'] for row in samples if row.get('firmware_cycles') is not None]
    daily_efc = 0
    energy_points = []
    for day, capacity in series:
        energy_points.append((daily_efc + energy[day] / 2, capacity))
        daily_efc += energy[day]
    same_pack = (len({(row.get('battery_model'), row.get('design_wh')) for row in samples}) == 1
                 and sorted(cycle_values) == cycle_values)
    return {
        'first': {key: first.get(key) for key in ('full_wh', 'design_wh', 'health_pct', 'firmware_cycles')},
        'latest': {key: last.get(key) for key in ('full_wh', 'design_wh', 'health_pct', 'firmware_cycles')},
        'firmware_cycle_delta': cycle_values[-1] - cycle_values[0]
        if same_pack and cycle_values else None,
        'daily_median_capacity_wh': {day.isoformat(): cap for day, cap in series},
        'daily_median_health_pct': {day.isoformat(): median(values) for day, values in health.items()},
        'capacity_trend_wh_per_month': slope([((day - series[0][0]).days / 30.4375, cap) for day, cap in series])
        if same_pack else None,
        'capacity_trend_wh_per_estimated_efc': slope(energy_points) if same_pack else None,
    }


def charging_sessions(samples, cuts):
    session = None

    def finish():
        if session is None or session['samples'] < 2:
            return None
        session['start_utc'] = utc(session['start_timestamp'])
        session['end_utc'] = utc(session['end_timestamp'])
        loads = session.pop('loads')
        session['mean_cpu_load_pct'] = sum(loads) / len(loads) if loads else None
        return session

    for row in samples:
        soc = row.get('soc_pct')
        charging = soc is not None and row.get('battery_status') == 'Charging' and row.get('ac_online') is not False
        connected = session is not None and compatible(previous, row, cuts, allow_full_transition=True)
        terminal = connected and row.get('genuinely_full') and row.get('ac_online') is not False
        if session is not None and (not connected or (not charging and not terminal)):
            result = finish()
            if result is not None:
                yield result
            session = None
        if session is None and charging:
            session = {'start_timestamp': row['timestamp'], 'start_soc_pct': soc, 'source': row['source'],
                       'adapter': adapter_key(row), 'firmware_mode': row.get('firmware_mode'),
                       'samples': 0, 'seconds_to_observation': {}, 'loads': []}
        if session is not None:
            if connected:
                load = cpu_load(previous, row)
                if load is not None:
                    session['loads'].append(load)
            session['samples'] += 1
            session['end_timestamp'] = row['timestamp']
            session['end_soc_pct'] = soc
            if soc < 98:
                session.pop('first_98_timestamp', None)
                session.pop('last_below_98_timestamp', None)
            if soc >= 98 and 'first_98_timestamp' not in session:
                session['first_98_timestamp'] = row['timestamp']
                if connected and previous.get('soc_pct', 100) < 98:
                    session['last_below_98_timestamp'] = previous['timestamp']
            for level in CHARGE_LEVELS:
                if level > session['start_soc_pct'] and (
                    row.get('genuinely_full') if level == 100 else soc >= level
                ):
                    session['seconds_to_observation'].setdefault(str(level), row['timestamp'] - session['start_timestamp'])
            if terminal:
                first_98 = session['first_98_timestamp']
                earlier = session.get('last_below_98_timestamp')
                session['tail_98_to_full'] = {
                    'first_ge_98_to_first_full_s': row['timestamp'] - first_98,
                    'lower_s': max(0, previous['timestamp'] - first_98) if earlier is not None else None,
                    'upper_s': row['timestamp'] - earlier if earlier is not None else None,
                }
                result = finish()
                if result is not None:
                    yield result
                session = None
        previous = row
    result = finish()
    if result is not None:
        yield result


def deadline_results(rows, samples, cuts, end, zone, sleeps=()):
    policies = []
    alarms = [row for row in rows if row['kind'] in ('alarm_armed', 'alarm_fired', 'alarm_clock_cancelled')
              and isinstance((row.get('detail') or {}).get('alarm_at'), (int, float))]
    for row in rows:
        if row['kind'] != 'policy' or not row.get('windows'):
            continue
        if not policies or any(row.get(key) != policies[-1].get(key) for key in ('windows', 'timezone')):
            policies.append(row)
    stamps = [row['timestamp'] for row in samples]
    for index, row in enumerate(policies):
        next_stamp = policies[index + 1]['timestamp'] if index + 1 < len(policies) else end
        try:
            policy_zone = ZoneInfo(row['timezone'])
        except (KeyError, ZoneInfoNotFoundError):
            policy_zone = zone
        days = (dt.datetime.fromtimestamp(next_stamp, policy_zone).date()
                - dt.datetime.fromtimestamp(row['timestamp'], policy_zone).date()).days
        seen = set()
        for offset in range(max(0, days) + 2):
            day = dt.datetime.fromtimestamp(row['timestamp'], policy_zone).date() + dt.timedelta(days=offset)
            for window in row['windows']:
                if day.weekday() not in window['days']:
                    continue
                start = wall_time(day, window['start'], policy_zone)
                ready = wall_time(day, window['ready'], policy_zone)
                if not row['timestamp'] <= ready < next_stamp or ready in seen:
                    continue
                seen.add(ready)
                eligible = samples[bisect_left(stamps, max(start, row['timestamp'])):bisect_right(stamps, ready)]
                result = {'ready_timestamp': ready, 'ready_utc': utc(ready), 'source': 'local_schedule',
                          'outcome': 'unknown', 'headroom_s': None, 'attempt_samples': len(eligible)}
                nearby = samples[bisect_left(stamps, start - WAKE_TOLERANCE_S):bisect_right(
                    stamps, start + WAKE_TOLERANCE_S)]
                evidence = wake_evidence(start, nearby, sleeps, alarms)
                result['wake'] = evidence
                first_full_after = next((sample for sample in samples[bisect_right(stamps, ready):bisect_right(
                    stamps, wall_time(day, window['end'], policy_zone))] if sample.get('genuinely_full')), None)
                result['first_full_after_deadline_utc'] = (
                    utc(first_full_after['timestamp']) if first_full_after else None)
                full = next((sample for sample in eligible if sample.get('genuinely_full')), None)
                covered = False
                # A cancelled or superseded window should not count as a policy miss.
                if any((sample.get('override') or {}).get('percent') == 80 for sample in eligible):
                    result['outcome'] = 'override_observed'
                elif full:
                    result.update(outcome='met', headroom_s=ready - full['timestamp'],
                                  observed_full_utc=utc(full['timestamp']))
                elif eligible and row['timestamp'] <= start:
                    first, last = eligible[0], eligible[-1]
                    covered = (first['timestamp'] - start <= first['period_s']
                               and ready - last['timestamp'] <= last['period_s']
                               and all(compatible(a, b, cuts) for a, b in zip(eligible, eligible[1:])))
                    if covered and all(sample.get('soc_pct') is not None and not sample.get('genuinely_full')
                                       for sample in eligible):
                        if all(sample['soc_pct'] < 100 for sample in eligible):
                            result['outcome'] = 'missed_estimated'
                result['limiting_evidence'] = deadline_cause(result['outcome'], evidence, eligible, covered, ready)
                if eligible:
                    last = eligible[-1]
                    result['last_pre_deadline'] = {
                        'utc': utc(last['timestamp']), **{
                            key: last.get(key) for key in ('soc_pct', 'ac_online', 'genuinely_full',
                                                          'battery_status', 'firmware_mode')
                        }}
                yield result


def summarize(rows, start, end, group_by, zone):
    groups = {key: new_group(a, b) for key, a, b in groups_for(start, end, group_by, zone)}
    cuts = sorted(row['timestamp'] for row in rows if row['kind'] in BOUNDARIES)
    ambiguous = {(row['source'], row['timestamp']) for row in rows if row['kind'] == 'legacy_conflict'}
    streams = defaultdict(list)
    observations = defaultdict(list)
    local = []
    for row in rows:
        if row['kind'] in ('sample', 'suspend', 'resume') and 'period_s' in row:
            streams['local'].append(row)
            local.append(row)
        elif row['kind'] == 'sample' and row['source'].startswith('upower_'):
            if (row['source'], row['timestamp']) in ambiguous:
                streams[row['source']].append(dict(row, battery_status=None, genuinely_full=False))
            else:
                streams[row['source']].append(row)
        if start <= row['timestamp'] < end:
            key = next(groups_for(row['timestamp'], end, group_by, zone))[0]
            groups[key]['observations'][f"{row['source']}/{row['kind']}"] += 1
            if row.get('full_wh') is not None or row.get('firmware_cycles') is not None:
                observations[key].append(row)
    coverage = defaultdict(list)
    daily_energy = defaultdict(lambda: Counter())
    sleeps = list(sleep_pairs(rows, local))
    models = [(sleep, gap_model(sleep)) for sleep in sleeps]
    for series in streams.values():
        for left, right in zip(series, series[1:]):
            first, last = max(start, left['timestamp']), min(end, right['timestamp'])
            if last <= first or not compatible(left, right, cuts):
                continue
            for key, a, b in groups_for(first, last, group_by, zone):
                group = groups[key]
                add_interval(group, left, right, a, b)
                if pair(left, right, 'soc_pct'):
                    coverage[key].append((a, b))
            if pair(left, right, 'design_wh') and pair(left, right, 'battery_power_w'):
                for day, a, b in groups_for(first, last, 'daily', zone):
                    target = dt.datetime.fromisoformat(day).date()
                    key = next(groups_for(a, end, group_by, zone))[0]
                    subtotal = new_group(a, b)
                    add_interval(subtotal, left, right, a, b)
                    daily_energy[key][target] += subtotal['equivalent_full_cycles']
    for stream in ('local', 'upower_charge'):
        for session in charging_sessions(streams[stream], cuts):
            if start <= session['start_timestamp'] < end:
                key = next(groups_for(session['start_timestamp'], end, group_by, zone))[0]
                groups[key]['charging_sessions'].append(session)
    episodes = list(conservation_episodes(local, cuts, compatible, adapter_key))
    for deadline in deadline_results(rows, local, cuts, end, zone, sleeps):
        if start <= deadline['ready_timestamp'] < end:
            key = next(groups_for(deadline['ready_timestamp'], end, group_by, zone))[0]
            groups[key]['charging_deadlines'].append(deadline)
    for key, a, b in groups_for(start, end, group_by, zone):
        group = groups[key]
        estimates = group['estimated_seconds']
        soc = estimates['soc']
        weighted = estimates.pop('soc_pct_seconds', 0)
        group['mean_soc_pct_while_covered'] = weighted / soc if soc else None
        group['soc_coverage_pct'] = 100 * soc / (b - a)
        gaps = list(unknown_ranges(a, b, coverage[key]))
        group['soc_unknown_seconds'] = sum(last - first for first, last in gaps)
        group['soc_unknown_intervals'] = len(gaps)
        bounds = gap_bounds(gaps, [(sleep, model) for sleep, model in models if a < sleep.end and b > sleep.start],
                            SOC_LEVELS)
        group['soc_missing_interval_bounds'] = bounds
        group['suspend_reconstruction'] = [
            describe_sleep(sleep, model) for sleep, model in models if a <= sleep.start < b]
        group['conservation_episodes'] = [episode for episode in episodes if a <= episode['timestamp'] < b]
        group['largest_soc_gaps'] = [
            {'from_utc': utc(first), 'to_utc': utc(last), 'seconds': last - first}
            for first, last in sorted(gaps, key=lambda gap: gap[1] - gap[0], reverse=True)[:10]
        ]
        group['capacity_and_firmware_cycles'] = capacity_summary(observations[key], daily_energy[key], zone)
        outcomes = group['deadline_outcomes'] = Counter(d['outcome'] for d in group['charging_deadlines'])
        denominator = outcomes['met'] + outcomes['missed_estimated']
        group['deadline_success_rate_pct'] = 100 * outcomes['met'] / denominator if denominator else None
        group['deadline_wake_evidence_counts'] = Counter(d['wake']['state'] for d in group['charging_deadlines'])
        group['deadline_limiting_evidence_counts'] = Counter(
            d['limiting_evidence'] for d in group['charging_deadlines'] if d.get('limiting_evidence'))
        sessions = defaultdict(lambda: defaultdict(list))
        tails = defaultdict(list)
        for session in group['charging_sessions']:
            bucket = int(session['start_soc_pct'] / 10) * 10
            load = session['mean_cpu_load_pct']
            workload = 'unknown' if load is None else ('heavy' if load >= HEAVY_CPU_PCT else 'under_70pct')
            for level, seconds in session['seconds_to_observation'].items():
                sessions[f"{session['adapter']}/{bucket}/{workload}"][level].append(seconds)
            tail = session.get('tail_98_to_full')
            if tail and tail['upper_s'] is not None:
                tails[session['adapter']].append(tail['first_ge_98_to_first_full_s'])
        group['tail_98_to_full_by_adapter'] = {key: timing_summary(values) for key, values in tails.items()}
        group['charge_timing_by_adapter_start_soc_workload'] = {
            name: {level: {'n': len(times), 'median_s': median(times), 'max_s': max(times)}
                   for level, times in levels.items()} for name, levels in sessions.items()
        }
    return groups


REPORT_VERSION = 1


def compact(group):
    result = dict(group)
    for key in ('charging_sessions', 'charging_deadlines', 'suspend_reconstruction', 'conservation_episodes'):
        items = result.pop(key)
        result[f'{key}_count'] = len(items)
        if key != 'charging_sessions':
            result[f'recent_{key}'] = items[-12:]
    capacity = result.get('capacity_and_firmware_cycles')
    if capacity:
        result['capacity_and_firmware_cycles'] = dict(capacity)
        for key in ('daily_median_capacity_wh', 'daily_median_health_pct'):
            values = capacity[key]
            by_month = defaultdict(list)
            for day, value in values.items():
                by_month[day[:7]].append(value)
            result['capacity_and_firmware_cycles'][key.replace('daily_', 'monthly_')] = {
                month: median(items) for month, items in by_month.items()}
            result['capacity_and_firmware_cycles'][key] = dict(list(values.items())[-90:])
    elapsed = group['elapsed_seconds']
    unknown = group['soc_unknown_seconds']
    # The covered duration is an interpolation. These are envelopes for gaps
    # added to that same estimate, as fractions of the entire elapsed period.
    result['soc_exposure_full_period_pct_envelope'] = {
        key: [round(100 * duration / elapsed, 4), round(100 * (duration + unknown) / elapsed, 4)]
        for key, duration in group['soc_above_seconds'].items()
    }
    conditional = group['soc_missing_interval_bounds']['conditional_above_threshold_seconds']
    result['soc_exposure_full_period_pct_conditional_envelope'] = {
        key: [round(100 * (duration + conditional[key][f'{bound}_seconds']) / elapsed, 4)
              for bound in ('lower', 'upper')]
        for key, duration in group['soc_above_seconds'].items()
    }
    return result


def optimization_report(rows, end, zone_name, zone, schema_version, baseline_before=None):
    if not rows:
        raise ValueError('No battery observations available')
    if baseline_before is not None and baseline_before > end:
        raise ValueError('The historical cutoff is in the future')
    local = [row for row in rows if row['source'] == 'local' and row['kind'] == 'sample']
    first_local = local[0]['timestamp'] if local else end
    legacy = [row for row in rows if row['source'].startswith('upower_') and row['kind'] == 'sample']
    starts = [row['timestamp'] for row in rows if row['kind'] == 'scheduler_started'
              and row['timestamp'] < first_local]
    cutoff = baseline_before if baseline_before is not None else min(starts, default=first_local)
    baseline = None
    if legacy and legacy[0]['timestamp'] < cutoff:
        historical = [row for row in rows if row['timestamp'] < cutoff and row['source'] != 'local']
        baseline_summary = summarize(historical, legacy[0]['timestamp'], cutoff, 'lifetime', zone)['lifetime']
        baseline = {'cutoff_source': 'explicit' if baseline_before else
                    ('earliest_retained_scheduler_start' if starts else 'first_local_sample'),
                    'mode_before_cutoff_verified': False, 'metrics': compact(baseline_summary)}
    first = legacy[0]['timestamp'] if legacy else first_local
    lifetime = compact(summarize(rows, first, end, 'lifetime', zone)['lifetime'])
    recent = {}
    for name, days in (('24h', 1), ('7d', 7), ('30d', 30), ('90d', 90)):
        start = max(first_local, end - days * 86400)
        if start < end:
            current = [row for row in rows if row['timestamp'] >= start - 86400]
            policies = [row for row in rows if row['kind'] == 'policy' and row['timestamp'] < start - 86400]
            if policies:
                current[:0] = policies[-1:]
            recent[name] = compact(summarize(current, start, end, 'lifetime', zone)['lifetime'])
            recent[name]['nominal_window_seconds'] = days * 86400
            recent[name]['truncated_at_first_live_sample'] = first_local > end - days * 86400

    adapters = {}
    for sample in local:
        if sample.get('ac_online') is not True:
            continue
        signature = adapter_key(sample)
        information = adapters.setdefault(signature, {
            'observations': 0, 'negative_battery_power_observations': 0,
            'type': sample.get('adapter_class'), 'usb_sources': [],
        })
        information['observations'] += 1
        if (sample.get('battery_power_w') or 0) < 0:
            information['negative_battery_power_observations'] += 1
        if sample.get('usb_sources'):
            information['usb_sources'] = [
                {k: v for k, v in port.items() if v is not None and (v != 0 or isinstance(v, bool))}
                for port in sample['usb_sources']
            ]
        ports = information['usb_sources']
        watts = ports[0].get('source_limit_w') if len(ports) == 1 else None
        if watts is not None:
            information['probable_power_class'] = '100_W_USB_C_class' if 95 <= watts <= 105 else 'USB_C_limit_observed'
        elif len(ports) == 1 and ports[0].get('type') == 'PD' and ports[0].get('current_now_a') == 5:
            information['probable_power_class'] = 'USB_C_PD_5A_request_observed_watts_unknown'
        elif information['type'] == 'mains_unidentified':
            information['probable_power_class'] = 'non_USB_C_mains_candidate'
        else:
            information['probable_power_class'] = 'unclassified'

    versions = defaultdict(Counter)
    for row in local:
        for key in ('collector_version', 'controller_version', 'schema_version'):
            versions[key][str(row.get(key, 'unrecorded'))] += 1
    changes = []
    anomalies = Counter()
    for row in rows:
        kind = row['kind']
        if row.get('policy_error'):
            anomalies['policy_read_error'] += 1
        if row.get('power_transition'):
            anomalies['unstable_power_snapshot'] += 1
        if kind in ('legacy_conflict', 'alarm_clock_cancelled'):
            anomalies[kind] += 1
        if kind in ('policy', 'firmware_change', 'hold', 'auto', 'set-window'):
            fields = ('requested_pct', 'firmware_mode', 'policy_reason', 'override', 'windows',
                      'trigger', 'detail', 'controller_version', 'collector_version')
            changes.append({'utc': utc(row['timestamp']), 'kind': kind,
                            **{key: row[key] for key in fields if key in row}})
            if row.get('windows'):
                schedule = json.dumps(row['windows'], sort_keys=True, separators=(',', ':')).encode()
                changes[-1]['schedule_sha256'] = hashlib.sha256(schedule).hexdigest()
    return {
        'report_version': REPORT_VERSION, 'database_schema_version': schema_version,
        'generated_utc': utc(end), 'timezone': zone_name, 'raw_samples_included': False,
        'methodology': {
            'coverage': 'Sample-supported estimates use adjacent compatible observations. Sleep models add zero coverage.',
            'comparison': 'Compare full-period envelopes and sample-supported coverage. Overlapping envelopes or different contexts cannot establish a reduction.',
            'gap_bounds': 'Raw unknown time permits zero to the full gap. Conditional envelopes assume no hidden AC or mode changes and monotone stored energy. A verified mode change at resume is allowed. A single stable USB-C source uses its reported fixed-profile limit as an additional conditional ceiling.',
            'full_charge': 'Requires SOC 100 with Full status, or Full level while no longer charging.',
            'deadlines': 'Observed full before the deadline is a success. A modeled gap cannot prove success. Wake timing and IRQ are correlations.',
            'adapter_identity': 'Source-limit class and optional PD vendor/product identifiers are fingerprints, not verified charger labels.',
            'voltage': '0.25 V pack-voltage bins. High-voltage cutoffs describe exposure and are not hardware safety limits.',
            'unavailable': ['verified battery temperature', 'battery internal resistance', 'GPU load and temperature'],
        },
        'historical_baseline': baseline, 'lifetime': lifetime, 'recent_live_periods': recent,
        'adapter_fingerprints': adapters,
        'versions_by_local_sample_count': dict(versions),
        'policy_changes': {'count': len(changes), 'latest': changes[-24:]},
        'anomalies': {'record_counts': anomalies,
                      'deadline_limiting_evidence_counts': lifetime['deadline_limiting_evidence_counts'],
                      'negative_on_ac_wh': lifetime['discharged_on_ac_by_adapter_wh']},
    }
