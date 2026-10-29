#!/usr/bin/env python3
"""Audit live shadow events against separately captured stock/unified Beast.

The Beast streams come from the same receiver and are comparison context, not
independent packet truth. This report deliberately makes no feeder decision.
"""
import argparse
import bisect
import gzip
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path

from analyze_stream_phase_paired import Beast, TICKS_PER_SECOND

HEADER = struct.Struct('>cQI')
OFFSET_TICKS = 2398
WINDOW_TICKS = 1440
ORIGIN = (52.4256, 13.1556)


def external_context(path):
    if path is None:
        return {}
    index = defaultdict(list)
    for line in path.read_text().splitlines():
        poll = json.loads(line)
        if 'error' in poll:
            continue
        for item in poll.get('aircraft', ()):
            try:
                observed = poll['source_unix']-item['seen_pos']
                lat, lon = float(item['lat']), float(item['lon'])
                address = item['hex'].lower()
                if len(address) != 6 or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    continue
                index[address].append((observed, lat, lon))
            except (ValueError, TypeError, KeyError):
                continue
    for rows in index.values():
        rows.sort()
    return index


def external_match(index, address, unix, local_bin):
    rows = index.get(address, ())
    i = bisect.bisect_left(rows, (unix,))
    nearest = min(rows[max(0,i-1):i+1], key=lambda row: abs(row[0]-unix), default=None)
    if nearest is None or abs(nearest[0]-unix) > 20:
        return False, False
    a1, o1 = map(math.radians, ORIGIN)
    a2, o2 = map(math.radians, nearest[1:])
    arc = 2*math.asin(math.sqrt(math.sin((a2-a1)/2)**2 +
                                math.cos(a1)*math.cos(a2)*math.sin((o2-o1)/2)**2))
    distance_nm = 3440.065*arc
    edges = ((0,50),(50,100),(100,150),(150,180),(180,200),(200,250),(250,float('inf')))
    external_bin = next((f'{int(lo)}-{int(hi) if math.isfinite(hi) else "plus"}'
                         for lo,hi in edges if lo <= distance_nm < hi), 'unknown')
    return True, external_bin == local_bin


def read_paired(path, allow_incomplete=False):
    streams = {b'S': defaultdict(list), b'U': defaultdict(list)}
    parsers = {key: Beast() for key in streams}
    addresses = defaultdict(list)
    coverage = {key: [None, None] for key in streams}
    chunks = Counter()
    opener = gzip.open if path.suffix == '.gz' else Path.open
    with opener(path, 'rb') as source:
        while header := source.read(HEADER.size):
            if len(header) != HEADER.size:
                if allow_incomplete:
                    break
                raise ValueError('truncated paired header')
            name, ns, length = HEADER.unpack(header)
            if not 0 < length <= 65536:
                raise ValueError('invalid paired chunk')
            payload = source.read(length)
            if len(payload) != length:
                if allow_incomplete:
                    break
                raise ValueError('truncated paired chunk')
            chunks[name.decode()] += 1
            if name not in parsers:
                continue
            coverage[name][0] = ns if coverage[name][0] is None else min(ns, coverage[name][0])
            coverage[name][1] = ns if coverage[name][1] is None else max(ns, coverage[name][1])
            for tick, message in parsers[name].feed(payload):
                if len(message) != 28 or int(message[:2], 16) >> 3 != 17:
                    continue
                streams[name][message].append(tick)
                if name == b'S':
                    addresses[message[2:8]].append(tick)
    for stream in (*streams.values(), addresses):
        for ticks in stream.values():
            ticks.sort()
    return streams, addresses, coverage, chunks


def nearby(times, tick):
    index = bisect.bisect_left(times, tick-WINDOW_TICKS)
    return index < len(times) and times[index] <= tick+WINDOW_TICKS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--paired', type=Path, required=True)
    parser.add_argument('--status', type=Path, required=True)
    parser.add_argument('--context', type=Path)
    parser.add_argument('--allow-incomplete', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    streams, addresses, coverage, chunks = read_paired(args.paired, args.allow_incomplete)
    status = json.loads(args.status.read_text())
    context = external_context(args.context)
    totals = Counter()
    by_kind = defaultdict(Counter)
    by_distance = defaultdict(Counter)
    evidence = []
    first_ns = max(coverage[b'S'][0], coverage[b'U'][0])
    last_ns = min(coverage[b'S'][1], coverage[b'U'][1])
    for line in args.events.read_text().splitlines():
        event = json.loads(line)
        if not isinstance(event.get('unix'), (int, float)):
            totals['preflight_without_wall_time'] += 1
            continue
        if event['unix'] < status['started_unix']:
            totals['before_current_run'] += 1
            continue
        kind = str(event['kind'])
        distance = event['distance_bin_nm']
        ns = round(event['unix']*1e9)
        tick = event['ticks']+OFFSET_TICKS
        if ns < first_ns+2_000_000_000 or ns > last_ns-2_000_000_000:
            totals['outside_complete_paired_wall_coverage'] += 1
            continue
        message = event['message_hex']
        stock = streams[b'S'].get(message, ())
        unified = streams[b'U'].get(message, ())
        prior = addresses.get(message[2:8], ())
        now_stock = nearby(stock, tick)
        now_unified = nearby(unified, tick)
        after = bisect.bisect_right(stock, tick+WINDOW_TICKS)
        future_exact = (after < len(stock) and
                        stock[after]-tick <= 30*TICKS_PER_SECOND)
        before = bisect.bisect_left(prior, tick-WINDOW_TICKS)
        prior_icao = (before > 0 and tick-prior[before-1] <= 30*TICKS_PER_SECOND)
        external_icao, external_range = external_match(context, message[2:8],
                                                        event['unix'], distance)
        flags = {'paired': True, 'stock_same_transmission': now_stock,
                 'unified_same_transmission': now_unified,
                 'later_stock_exact_payload_30s': future_exact,
                 'prior_stock_icao_30s': prior_icao,
                 'external_icao_fresh': external_icao,
                 'external_distance_bin_agrees': external_range}
        totals.update(key for key, yes in flags.items() if yes)
        by_kind[kind].update(key for key, yes in flags.items() if yes)
        by_distance[distance].update(key for key, yes in flags.items() if yes)
        if len(evidence) < 40 and (future_exact or distance in ('180-200','200-250','250-plus')):
            evidence.append({'unix': event['unix'], 'kind': kind, 'distance': distance,
                             'message_hex': message, **flags})
    result = {'scope': 'live research shadow, same receiver stock/unified corroboration only',
              'source_commit': status['source_commit'], 'shadow_status': status['counts'],
              'external_source': 'adsb.fi aircraft positions; no raw packets',
              'coverage_unix': {'first': first_ns/1e9, 'last': last_ns/1e9},
              'paired_chunks': dict(chunks), 'counts': dict(totals),
              'by_kind': {k: dict(v) for k, v in by_kind.items()},
              'by_distance_nm': {k: dict(v) for k, v in by_distance.items()},
              'evidence_examples': evidence,
              'limits': ('A later exact stock recurrence supports payload plausibility but '
                         'is not independent receiver confirmation. Beast lacks corrected-bit flags; '
                         'neither the original live counts nor this replay is a false-positive rate.')}
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'counts': result['counts'], 'by_kind': result['by_kind'],
                      'by_distance_nm': result['by_distance_nm']}, indent=2))


if __name__ == '__main__':
    main()
