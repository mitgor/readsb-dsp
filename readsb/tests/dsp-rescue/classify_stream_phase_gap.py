#!/usr/bin/env python3
"""Classify saved Stream1090 outputs using a diagnostic-only traced build.

The traced Stream1090 writes C/T/E/D-prefixed copies of emitted DF17 frames
to stderr: clean, fixed CRC table, confidence-based erasure, DF19 promotion.
This
script never connects to a receiver or feeder. The diagnostic build must be
made from the same pinned upstream commit as the original comparison.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

from compare_stream_phase_live import HALO, RATE, TOTAL, read_packets
from analyze_stream_phase_paired import read_taps, match, STOCK_OFFSET


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', required=True, type=Path)
    p.add_argument('--candidates', required=True, type=Path)
    p.add_argument('--paired', required=True, type=Path)
    p.add_argument('--traced-binary', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--limit-seconds', type=int, default=0)
    args = p.parse_args()
    stock, *_ = read_taps(args.paired)
    stock = stock[b'S']
    records = (json.loads(s) for s in args.candidates.open())
    epoch = expected = first = None
    samples = bytearray()
    total = Counter()
    processed = 0
    with args.output.open('w') as output:
        for packet_epoch, sample, ns, dropped, raw in read_packets(args.capture):
            if packet_epoch != epoch or sample != expected:
                epoch = packet_epoch
                skip = -sample % 3
                first = sample + skip
                samples.clear()
                samples.extend(raw[2*skip:])
            else:
                samples.extend(raw)
            expected = sample + len(raw)//2
            while len(samples) >= TOTAL*2:
                reference = next(records)
                assert reference['epoch'] == epoch and reference['first_sample'] == first
                proc = subprocess.run([str(args.traced_binary), '-s', '2.4', '-u', '8'],
                                      input=bytes(samples[:TOTAL*2]), capture_output=True,
                                      timeout=5, check=True)
                traced = {}
                for line in proc.stderr.splitlines():
                    if len(line) != 43 or line[:1] not in (b'C', b'T', b'E', b'D') or line[1:2] != b'@' or line[-1:] != b';':
                        continue
                    try:
                        tick = int(line[2:14], 16) + first*5 - 1630
                        payload = line[14:-1].decode().lower()
                    except (ValueError, UnicodeDecodeError):
                        continue
                    traced[(tick, payload)] = {b'C': 'clean', b'T': 'table',
                                               b'E': 'erasure', b'D': 'df19'}[line[:1]]
                counts = Counter()
                old_only_provenance = []
                for family in ('both', 'native_only', 'old_only'):
                    for tick, payload, *rest in reference[family+'_rows']:
                        if family == 'native_only':
                            continue
                        if family == 'both':
                            tick += rest[0]  # both_rows stores the native clock first
                        kind = traced.get((tick, payload), 'unmatched')
                        if family == 'old_only':
                            old_only_provenance.append((tick, payload, kind))
                        counts[family+'_'+kind] += 1
                        if family == 'old_only' and match(stock, payload, tick+STOCK_OFFSET):
                            counts[family+'_'+kind+'_in_stock'] += 1
                        elif family == 'old_only':
                            counts[family+'_'+kind+'_beyond_stock'] += 1
                output.write(json.dumps({'second': processed, 'counts': counts,
                                         'old_only_provenance_rows': old_only_provenance})+'\n')
                total.update(counts)
                processed += 1
                del samples[:RATE*2]
                first += RATE
                if processed % 100 == 0:
                    output.flush()
                    print(json.dumps({'processed': processed, 'total': total}), flush=True)
                if args.limit_seconds and processed >= args.limit_seconds:
                    break
            if args.limit_seconds and processed >= args.limit_seconds:
                break
    summary = {'processed_seconds': processed, 'counts': dict(total)}
    args.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
