"""Sleep reconstruction and charging evidence derived from recorded observations."""

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from statistics import median

from battery_store import utc

WAKE_TOLERANCE_S = 90
GAP_MINIMUM_S = 120


@dataclass
class Sleep:
    before: dict
    after: dict
    interruptions: list
    verified_mode_change_at_resume: bool = False

    @property
    def start(self):
        return self.before['timestamp']

    @property
    def end(self):
        return self.after['timestamp']


def sleep_pairs(rows, local):
    """Pair complete same-boot hook observations and verify elapsed sleep with both clocks."""
    before = None
    events = [row for row in rows if row['kind'] in {
        'boot', 'power_source', 'firmware_change', 'hold', 'auto', 'set-window',
        'collector_start', 'collector_stop',
    }]
    stamps = [row['timestamp'] for row in events]
    for row in local:
        if row['kind'] == 'suspend':
            before = row
        elif row['kind'] == 'resume' and before is not None:
            if (row['boot_id'] == before['boot_id'] and row.get('boot_id')
                    and row.get('detail') != 'hibernate' and before.get('detail') != 'hibernate'):
                boot = row['boottime_s'] - before['boottime_s']
                awake = row['monotonic_s'] - before['monotonic_s']
                start, end = before['timestamp'], row['timestamp']
                if boot - awake >= 1 and abs(boot - (end - start)) <= 2 and 0 <= awake <= 15:
                    between = events[bisect_right(stamps, start):bisect_left(stamps, end)]
                    # A policy reconcile can run beside the post-sleep hook.
                    # Use its producer timestamp even if the collector received it later.
                    mode_changed = before.get('firmware_mode') != row.get('firmware_mode')
                    target = {'Long_Life': 80, 'Standard': 100}.get(row.get('firmware_mode'))
                    near = events[bisect_left(stamps, end - 15):bisect_right(stamps, end + 5)]
                    verified = []
                    if mode_changed and target is not None:
                        for event in near:
                            detail = event.get('detail') or {}
                            if (event['kind'] == 'firmware_change' and event.get('boot_id') == row['boot_id']
                                    and detail.get('trigger') in ('scheduler', 'resume_reconcile')
                                    and isinstance(detail.get('applied_at'), (int, float))
                                    and 0 <= end - detail['applied_at'] <= 15 and detail.get('percent') == target):
                                verified.append(event)
                    interruptions = [event['kind'] for event in between if event not in verified]
                    yield Sleep(before, row, interruptions, bool(verified))
            before = None


def usb_signature(row):
    return sorted((p['port'], p.get('type'), p.get('source_limit_w') or 0,
                   p.get('partner_vid') or '', p.get('partner_pid') or '',
                   p.get('voltage_now_v') or 0, p.get('current_now_a') or 0)
                  for p in row.get('usb_sources', []))


def endpoint(row):
    fields = ('soc_pct', 'stored_wh', 'full_wh')
    if any(row.get(key) is None for key in fields):
        return None
    soc, stored, full = (row[key] for key in fields)
    if full <= 0 or not 0 <= stored <= full * 1.02 or not 0 <= soc <= 100:
        return None
    energy_pct = min(100, stored / full * 100)
    if abs(energy_pct - soc) > 2:
        return None
    # Include the gauge's integer rounding and disagreement with its energy reading.
    return max(0, min(soc - 0.5, energy_pct)), min(100, max(soc + 0.5, energy_pct))


def gap_model(sleep):
    """Conditional monotone energy model. No estimate is promoted to measured coverage."""
    a, b = sleep.before, sleep.after
    endpoints = endpoint(a), endpoint(b)
    if (sleep.end - sleep.start < GAP_MINIMUM_S or sleep.interruptions
            or any(value is None for value in endpoints) or not a.get('battery_model')
            or a.get('battery_model') != b.get('battery_model')
            or a.get('full_wh') != b.get('full_wh')
            or a.get('power_transition') or b.get('power_transition')
            or a.get('ac_online') is None or a.get('ac_online') != b.get('ac_online')
            or a.get('firmware_mode') is None
            or (a.get('firmware_mode') != b.get('firmware_mode') and not sleep.verified_mode_change_at_resume)):
        return None
    first, last = endpoints
    delta = b['stored_wh'] - a['stored_wh']
    if (a['ac_online'] is False and delta <= 0 and last[0] <= first[1]
            and all((row.get('battery_power_w') or 0) <= 0
                    and row.get('battery_status') != 'Charging' for row in (a, b))):
        return 'monotone_on_battery', first, last, None
    if (a['ac_online'] is True and delta >= 0 and last[1] >= first[0]
            and a.get('adapter_class') == b.get('adapter_class')
            and usb_signature(a) == usb_signature(b)
            and all((row.get('battery_power_w') or 0) >= 0 for row in (a, b))
            and all(row.get('battery_status') in ('Charging', 'Full', 'Not charging') for row in (a, b))):
        ports = usb_signature(a)
        ceiling = ports[0][2] if len(ports) == 1 and ports[0][2] > 0 else None
        if ceiling and delta * 3600 > ceiling * (sleep.end - sleep.start):
            return None
        return 'monotone_on_same_ac', first, last, ceiling
    return None


def exposure_windows(sleep, model, level):
    """Return conditional guaranteed and possible time windows above a threshold."""
    direction, first, last, ceiling = model
    start, end = sleep.start, sleep.end
    increasing = direction == 'monotone_on_same_ac'
    floor, peak = (first, last) if increasing else (last, first)
    whole = start, end
    if floor[0] > level:
        return whole, whole
    if peak[1] <= level:
        return None, None
    if increasing and ceiling:
        seconds_per_pct = sleep.before['full_wh'] * 36 / ceiling
        earliest = min(end, start + max(0, level - first[1]) * seconds_per_pct)
        latest = max(start, end - max(0, last[0] - level) * seconds_per_pct)
        if earliest > latest:
            return None, whole
        return (latest, end), (earliest, end)
    return None, whole


def overlap(first, last, interval):
    return max(0, min(last, interval[1]) - max(first, interval[0])) if interval else 0


def gap_bounds(gaps, sleeps, thresholds):
    tiers = {str(level): {'lower_seconds': 0, 'upper_seconds': 0} for level in thresholds}
    unknown = sum(b - a for a, b in gaps)
    modeled = 0
    starts, ends = [a for a, _ in gaps], [b for _, b in gaps]
    for sleep, model in sleeps:
        if model is None:
            continue
        first, last = bisect_right(ends, sleep.start), bisect_left(starts, sleep.end)
        intersections = [(max(a, sleep.start), min(b, sleep.end)) for a, b in gaps[first:last]]
        if not intersections:
            continue
        modeled += sum(b - a for a, b in intersections)
        for level in thresholds:
            certain, possible = exposure_windows(sleep, model, level)
            stats = tiers[str(level)]
            stats['lower_seconds'] += sum(overlap(a, b, certain) for a, b in intersections)
            stats['upper_seconds'] += sum(overlap(a, b, possible) for a, b in intersections)
    for bounds in tiers.values():
        bounds['upper_seconds'] += max(0, unknown - modeled)
    return {'modeled_gap_seconds': modeled, 'unmodeled_gap_seconds': max(0, unknown - modeled),
            'conditional_above_threshold_seconds': tiers,
            'unconditional_above_threshold_seconds': {'lower_seconds': 0, 'upper_seconds': unknown}}


def describe_sleep(sleep, model):
    a, b = sleep.before, sleep.after
    result = dict(
        from_utc=utc(sleep.start), to_utc=utc(sleep.end), duration_s=sleep.end - sleep.start,
        soc_before=a.get('soc_pct'), soc_after=b.get('soc_pct'), ac_before=a.get('ac_online'),
        ac_after=b.get('ac_online'), firmware_before=a.get('firmware_mode'), firmware_after=b.get('firmware_mode'),
        verified_full_on_resume=b.get('genuinely_full'), rtc_alarm_before=a.get('rtc_wakealarm'),
        rtc_alarm_after=b.get('rtc_wakealarm'), resume_irq=b.get('wake_irq'),
        observed_interruptions=sleep.interruptions, conditional_model=model[0] if model else None,
        verified_mode_change_at_resume=sleep.verified_mode_change_at_resume,
        conditional_usb_source_ceiling_w=model[3] if model else None,
    )
    if a.get('stored_wh') is not None and b.get('stored_wh') is not None:
        result['net_change_wh'] = b['stored_wh'] - a['stored_wh']
    if a.get('next_deadline') and sleep.start <= a['next_deadline']['start'] <= sleep.end:
        result['planned_start_inside_gap_utc'] = utc(a['next_deadline']['start'])
    return result


def wake_evidence(start, samples, sleeps, alarms):
    sleep = next((item for item in sleeps if item.start < start <= item.end), None)
    matching = [event for event in alarms if abs(event['detail']['alarm_at'] - start) <= 1]
    fired = next((event for event in matching if event['kind'] == 'alarm_fired'), None)
    result = {'scheduled_start_utc': utc(start), 'alarm_expiration_observed_utc':
              utc(fired['timestamp']) if fired else None, 'state': 'unknown'}
    if sleep:
        events = [event for event in alarms if event['kind'] != 'alarm_fired'
                  and event['timestamp'] <= sleep.start and event.get('boot_id') == sleep.before.get('boot_id')]
        armed = bool(events and events[-1]['kind'] == 'alarm_armed'
                     and abs(events[-1]['detail']['alarm_at'] - start) <= 1)
        result.update(armed_before_sleep=armed, resume_utc=utc(sleep.end),
                      resume_delay_s=sleep.end - start, resume_irq=sleep.after.get('wake_irq'))
        if sleep.end - start <= WAKE_TOLERANCE_S:
            result['state'] = 'resume_near_armed_alarm' if armed else 'resume_near_planned_start'
        else:
            result['state'] = 'still_asleep_past_armed_alarm' if armed else 'still_asleep_past_planned_start'
    elif any(abs(row['timestamp'] - start) <= WAKE_TOLERANCE_S and row['kind'] == 'sample' for row in samples):
        result['state'] = 'awake_observed_near_start'
    elif fired:
        result['state'] = 'alarm_expired_sleep_state_unknown'
    return result


def deadline_cause(outcome, evidence, eligible, covered, ready):
    if outcome == 'met':
        return None
    if outcome == 'override_observed':
        return '80_pct_override'
    if evidence['state'].startswith('still_asleep_past_'):
        return evidence['state']
    if not eligible:
        return 'missing_window_observations'
    last = eligible[-1]
    if ready - last['timestamp'] <= last['period_s']:
        if last.get('ac_online') is False:
            return 'ac_absent_near_deadline'
        if last.get('requested_pct') == 100 and last.get('firmware_mode') == 'Long_Life':
            return 'conservation_observed_during_full_request'
        if (covered and all(row.get('ac_online') is True for row in eligible)
                and last.get('soc_pct') is not None and last['soc_pct'] < 100
                and last.get('battery_status') == 'Charging'):
            return 'still_charging_near_deadline'
    return 'insufficient_evidence' if outcome == 'unknown' else 'cause_unresolved'


def conservation_episodes(samples, cuts, compatible, adapter_key):
    """Track observed mode changes. A gap or end of recording censors duration."""
    previous = None
    episode = None
    for row in samples:
        current = row.get('firmware_mode') == 'Long_Life'
        if episode is not None:
            linked = compatible(previous, row, cuts)
            if not linked or not current or row.get('soc_pct') is None:
                yield dict(episode, end_reason='gap_or_mode_change')
                episode = None
            elif row['soc_pct'] <= 80:
                episode['at_or_below_80_observed_by_s'] = row['timestamp'] - episode['timestamp']
                yield dict(episode, end_reason='at_or_below_80_observed')
                episode = None
            else:
                interval = row['timestamp'] - previous['timestamp']
                elapsed = row['timestamp'] - episode['timestamp']
                episode['last_above_80_observed_s'] = elapsed
                if row.get('ac_online') is True and previous.get('ac_online') is True:
                    if row.get('battery_power_w') is not None and previous.get('battery_power_w') is not None:
                        episode['above_80_ac_power_covered_s'] += interval
                    if min(row.get('battery_power_w') or 0, previous.get('battery_power_w') or 0) > 0:
                        episode['charging_observed_above_80_on_ac_s'] += interval
        if (previous and current and previous.get('firmware_mode') in ('Standard', 'Fast')
                and (row.get('soc_pct') or 0) > 80 and row.get('boot_id') == previous.get('boot_id')
                and row['timestamp'] - previous['timestamp'] <= 2 * previous['period_s']):
            episode = dict(timestamp=row['timestamp'], start_utc=utc(row['timestamp']), soc_pct=row['soc_pct'],
                           genuinely_full=row.get('genuinely_full'), ac_online=row.get('ac_online'),
                           adapter=adapter_key(row), last_above_80_observed_s=0,
                           above_80_ac_power_covered_s=0, charging_observed_above_80_on_ac_s=0)
        previous = row
    if episode is not None:
        yield dict(episode, end_reason='recording_ends')


def timing_summary(values):
    return {'n': len(values), 'median_s': median(values), 'max_s': max(values)} if values else {'n': 0}
