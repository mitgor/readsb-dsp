#!/usr/bin/env python3
"""Compare phase/Stream candidates against read-only stock and unified Beast taps."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
import struct

HEADER = struct.Struct('>cQI')
LENGTHS = {0x31: 9, 0x32: 14, 0x33: 21}
TICKS_PER_SECOND = 12_000_000
STOCK_OFFSET = 2400  # verified by shared exact packets: native preamble -> readsb Beast


class Beast:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, chunk):
        self.buf.extend(chunk)
        data, rows, i = self.buf, [], 0
        while i+1 < len(data):
            if data[i] != 26 or data[i+1] not in LENGTHS:
                i += 1
                continue
            kind = data[i+1]
            j, body, incomplete, bad = i+2, bytearray(), False, False
            while len(body) < LENGTHS[kind]:
                if j >= len(data):
                    incomplete = True
                    break
                value = data[j]
                if value == 26:
                    if j+1 >= len(data):
                        incomplete = True
                        break
                    if data[j+1] != 26:
                        bad = True
                        break
                    j += 1
                body.append(value)
                j += 1
            if incomplete:
                break
            if bad:
                i = max(i+1, j)
                continue
            if kind == 0x33:
                rows.append((int.from_bytes(body[:6], 'big'), body[7:].hex()))
            i = j
        del data[:i]
        if len(data) > 256:
            raise ValueError('unbounded partial Beast record')
        return rows


def read_taps(path):
    parsers = {b'S': Beast(), b'U': Beast()}
    events = {b'S': defaultdict(list), b'U': defaultdict(list)}
    addresses = defaultdict(list)
    snapshots = []
    chunks = Counter()
    chunk_times = {b'S': [], b'U': []}
    with path.open('rb') as f:
        while header := f.read(HEADER.size):
            if len(header) != HEADER.size:
                break
            source, ns, size = HEADER.unpack(header)
            if size > 1_000_000:
                raise ValueError('oversized tap chunk')
            chunk = f.read(size)
            if len(chunk) != size:
                break
            chunks[source.decode()] += 1
            if source == b'J':
                try:
                    doc = json.loads(chunk)
                    position = {a[0].lower(): (a[1], a[2]) for a in doc['aircraft']}
                    snapshots.append((ns, position))
                except (KeyError, ValueError, TypeError, IndexError):
                    continue
            elif source in parsers:
                chunk_times[source].append(ns)
                for tick, message in parsers[source].feed(chunk):
                    if len(message) != 28:
                        continue
                    events[source][message].append(tick)
                    if source == b'S':
                        addresses[message[2:8]].append(tick)
    for stream in events.values():
        for ticks in stream.values():
            ticks.sort()
    for ticks in addresses.values():
        ticks.sort()
    return events, addresses, snapshots, chunks, chunk_times


def match(index, message, tick):
    ticks = index.get(message, ())
    pos = bisect_left(ticks, tick-1440)
    return pos < len(ticks) and ticks[pos] <= tick+1440


def prior_address(index, message, tick):
    ticks = index.get(message[2:8], ())
    pos = bisect_left(ticks, tick-1440)
    return pos > 0 and tick-ticks[pos-1] <= 30*TICKS_PER_SECOND


def distance_bin(snapshots, snapshot_times, ns, message):
    if not snapshots:
        return 'unknown'
    i = bisect_right(snapshot_times, ns)-1
    if i < 0 or ns-snapshot_times[i] > 10_000_000_000:
        return 'unknown'
    position = snapshots[i][1].get(message[2:8])
    if not position:
        return 'unknown'
    nm, seen_pos = position
    if not isinstance(nm, (int, float)) or seen_pos > 15:
        return 'unknown'
    for edge in (50, 100, 150, 180, 200, 250):
        if nm < edge:
            return f'<{edge}nm'
    return '250+nm'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidates', type=Path, required=True)
    ap.add_argument('--paired', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--split-unix', type=float, default=0,
                    help='Optional shadow-service restart time for segmented counts')
    args = ap.parse_args()
    events, addresses, snapshots, chunks, chunk_times = read_taps(args.paired)
    snapshot_times = [row[0] for row in snapshots]
    def covered(ns):
        for source in (b'S', b'U'):
            times = chunk_times[source]
            i = bisect_right(times, ns)
            if i == 0 or i == len(times):
                return False
            if ns-times[i-1] > 2_000_000_000 or times[i]-ns > 2_000_000_000:
                return False
        return True
    totals = Counter()
    ranges = defaultdict(Counter)
    segments = defaultdict(Counter)
    offsets = []
    observations = []
    for row in map(json.loads, args.candidates.open()):
        first, wall = row['first_sample'], row['wall_start_ns']
        for family, entries in (('both', row['both_rows']),
                                ('native_only', row['native_only_rows']),
                                ('old_only', row['old_only_rows'])):
            for entry in entries:
                tick, message = entry[:2]
                beast_tick = tick+STOCK_OFFSET
                relative_ns = (tick-first*5)*1_000_000_000//TICKS_PER_SECOND
                ns = wall+relative_ns
                totals[family+'_all'] += 1
                if not covered(ns):
                    totals[family+'_outside_paired_coverage'] += 1
                    continue
                segment = 'before_restart' if args.split_unix and ns < args.split_unix*1e9 else 'after_restart'
                stock = match(events[b'S'], message, beast_tick)
                unified = match(events[b'U'], message, beast_tick)
                prior = prior_address(addresses, message, beast_tick)
                band = distance_bin(snapshots, snapshot_times, ns, message)
                totals[family] += 1
                segments[segment][family] += 1
                ranges[family][band] += 1
                if stock:
                    totals[family+'_in_stock'] += 1
                    ticks = events[b'S'][message]
                    i = bisect_left(ticks, beast_tick)
                    nearest = min(ticks[max(0, i-1):i+1], key=lambda x:abs(x-beast_tick))
                    offsets.append(nearest-tick)
                if unified:
                    totals[family+'_in_unified'] += 1
                if not stock:
                    totals[family+'_beyond_stock'] += 1
                    segments[segment][family+'_beyond_stock'] += 1
                    ranges[family+'_beyond_stock'][band] += 1
                if not unified:
                    totals[family+'_beyond_unified'] += 1
                    segments[segment][family+'_beyond_unified'] += 1
                    if prior:
                        totals[family+'_beyond_unified_with_prior_stock_address'] += 1
                        ranges[family+'_beyond_unified_with_prior_stock_address'][band] += 1
                        if len(observations) < 100:
                            observations.append({'family': family, 'tick': tick,
                                                 'message': message, 'range': band})
    offset_median = statistics.median(offsets) if offsets else None
    offset_mad = statistics.median(abs(x-offset_median) for x in offsets) if offsets else None
    report = {'candidate_counts': dict(totals), 'segments': {k: dict(v) for k,v in segments.items()},
              'ranges': {k: dict(v) for k,v in ranges.items()},
              'stock_offset_ticks_median': offset_median,
              'stock_offset_ticks_mad': offset_mad,
              'paired_chunks': dict(chunks), 'stock_payloads': len(events[b'S']),
              'unified_payloads': len(events[b'U']), 'snapshots': len(snapshots),
              'examples': observations}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('examples','ranges')}))


if __name__ == '__main__':
    main()
