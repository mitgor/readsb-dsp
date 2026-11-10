"""Unchanged live Stream1090 CRC, clock-calibration and dedup rules."""
import bisect,statistics
from collections import defaultdict

def valid_df17(payload):
    if len(payload)!=28:return False
    try:value=int(payload,16)
    except ValueError:return False
    if value>>107!=17:return False
    for bit in range(111,23,-1):
        if value&(1<<bit):value^=0x1fff409<<(bit-24)
    return value==0


def parse_avr(data, first):
    for line in data.splitlines():
        if not line or line[0:1] not in (b'@', b'<') or not line.endswith(b';'):
            continue
        try:
            tick = int(line[1:13], 16) + first * 5
            payload = line[15:-1] if line[0:1] == b'<' else line[13:-1]
            if len(payload) != 28:
                continue
            message = payload.decode('ascii').lower()
        except (ValueError, UnicodeError):
            continue
        if valid_df17(message):
            yield tick, message


def compare(candidates, frames):
    """Calibrate sample clocks on identical stock frames before calling extras."""
    by_payload = defaultdict(list)
    for tick, message in frames:
        by_payload[message].append(tick)
    for rows in by_payload.values():
        rows.sort()
    offsets = []
    for tick, message in candidates:
        rows = by_payload.get(message, ())
        if not rows:
            continue
        i = bisect.bisect_left(rows, tick)
        nearby = rows[max(0,i-1):i+1]
        if nearby:
            delta = min(nearby, key=lambda t:abs(t-tick)) - tick
            if abs(delta) <= 60000:
                offsets.append(delta)
    if len(offsets) < 10:
        return {'aligned':False,'reason':'too_few_shared_frames','shared':len(offsets)}, []
    offset = int(statistics.median(offsets))
    mad = statistics.median(abs(x-offset) for x in offsets)
    if mad > 360:
        return {'aligned':False,'reason':'unstable_clock_offset','shared':len(offsets),'mad_ticks':mad}, []
    extras = []
    extra_times = defaultdict(list)
    for tick, message in candidates:
        rows = by_payload.get(message, ())
        target = tick + offset
        i = bisect.bisect_left(rows, target-1440)
        if i == len(rows) or rows[i] > target+1440:
            prior=extra_times[message]
            j=bisect.bisect_left(prior,target-1440)
            if j==len(prior) or prior[j]>target+1440:
                extras.append((target,message));bisect.insort(prior,target)
    return {'aligned':True,'shared':len(offsets),'offset_ticks':offset,'mad_ticks':mad}, extras
