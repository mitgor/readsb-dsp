#!/usr/bin/env python3
"""Replay native phase repairs on saved RF, with stock-address prefilter.

The bitmap is populated only from stock Beast sightings preceding each RF
second; it never contains future addresses. Beast does not expose readsb's
corrected-bit flag, so these are permissive offline upper-bound counts. The
production guard still requires a recent, uncorrected stock address.
"""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import ctypes
import json
from pathlib import Path
import time

from compare_stream_phase_live import RATE, HALO, TOTAL, read_packets, pair, unique, zero_crc
from analyze_stream_phase_paired import read_taps, match, prior_address, STOCK_OFFSET

CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int64,
                            ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', required=True, type=Path)
    p.add_argument('--candidates', required=True, type=Path)
    p.add_argument('--paired', required=True, type=Path)
    p.add_argument('--native-lib', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--limit-seconds', type=int, default=0)
    args = p.parse_args()
    events, addresses, snapshots, chunks, chunk_times = read_taps(args.paired)
    def covered(ns):
        for source in (b'S', b'U'):
            times = chunk_times[source]
            i = bisect_right(times, ns)
            if i == 0 or i == len(times) or ns-times[i-1] > 2_000_000_000 or times[i]-ns > 2_000_000_000:
                return False
        return True
    sightings = sorted((tick, int(addr, 16)) for addr, ticks in addresses.items()
                       for tick in ticks)
    bitmap = (ctypes.c_uint8 * (1 << 21))()
    bitmap_index = 0
    lib = ctypes.CDLL(str(args.native_lib.resolve()))
    lib.dspStreamPhaseRepair.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint,
                                         ctypes.c_int64, ctypes.c_int64, CALLBACK,
                                         ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8),
                                         ctypes.c_int64]
    records = (json.loads(s) for s in args.candidates.open())
    epoch = expected = first = None
    samples = bytearray()
    totals = Counter()
    processed = 0
    with args.output.open('w') as output:
        for packet_epoch, sample, ns, dropped, raw in read_packets(args.capture):
            if packet_epoch != epoch or sample != expected:
                if epoch is not None:
                    ctypes.memset(bitmap, 0, 1 << 21)
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
                start = (first+HALO)*5+STOCK_OFFSET
                while bitmap_index < len(sightings) and sightings[bitmap_index][0] < start:
                    addr = sightings[bitmap_index][1]
                    bitmap[addr >> 3] |= 1 << (addr & 7)
                    bitmap_index += 1
                results = []
                def emit(pointer, bit_sample, corrected, kind, opaque):
                    message = ctypes.string_at(pointer, 14)
                    if message[0] >> 3 == 17 and zero_crc(message):
                        tick = (bit_sample-64)*3//2
                        if (first+HALO)*5 <= tick < (first+HALO+RATE)*5:
                            results.append((tick, message.hex(), corrected, kind))
                callback = CALLBACK(emit)
                buf = ctypes.create_string_buffer(bytes(samples[:TOTAL*2]))
                cpu0 = time.process_time()
                lib.dspStreamPhaseRepair(ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8)),
                                         TOTAL, first, first+HALO, callback, None,
                                         bitmap, 2**63-1)
                cpu = time.process_time()-cpu0
                by_kind = defaultdict(list)
                for tick, msg, corrected, kind in results:
                    by_kind[kind].append((tick, msg))
                old = [(t, m) for t,m in reference['old_only_rows']]
                old += [(t+d, m) for t,m,d in reference['both_rows']]
                native, old = [(t,m) for t,m,_,_ in results], old
                both, native_only, old_only = pair(native, old)
                old_only_reference = [(t,m) for t,m in reference['old_only_rows']]
                recovered_original, _, missed_original = pair(native, old_only_reference)
                matched_original = len(recovered_original)
                clean_reference = [(t,m) for t,m in reference['native_only_rows']]
                clean_reference += [(t,m) for t,m,d in reference['both_rows']]
                clean_missing = len(pair(by_kind[0],clean_reference)[2])
                kind_of = {}
                for t,m,corrected,kind in results:
                    kind_of[(t,m)] = min(kind_of.get((t,m), kind), kind)
                counts = Counter({'native_cpu_us': round(cpu*1_000_000),
                                  'native_unique': len(unique(native)),
                                  'old_matched': len(both),
                                  'old_missed': len(old_only),
                                  'old_only_recovered': matched_original,
                                  'new_only': len(native_only),
                                  'clean_missing': clean_missing})
                for tick,msg,delta in recovered_original:
                    ns = reference['wall_start_ns'] + (tick-first*5)*1_000_000_000//12_000_000
                    if covered(ns):
                        counts['old_only_recovered_paired'] += 1
                        if not match(events[b'S'], msg, tick+STOCK_OFFSET):
                            counts['old_only_recovered_beyond_stock'] += 1
                for tick,msg in missed_original:
                    ns = reference['wall_start_ns'] + (tick-first*5)*1_000_000_000//12_000_000
                    if covered(ns):
                        counts['old_only_missed_paired'] += 1
                        if not match(events[b'S'], msg, tick+STOCK_OFFSET):
                            counts['old_only_missed_beyond_stock'] += 1
                for kind, rows in by_kind.items():
                    counts[{0:'clean',1:'table',2:'erasure'}[kind]] = len(unique(rows))
                    recovered = len(pair(rows, old_only_reference)[0])
                    counts[{0:'clean',1:'table',2:'erasure'}[kind]+'_old_only_recovered'] = recovered
                for tick, msg in native_only:
                    kind = kind_of[(tick,msg)]
                    name = {0:'clean',1:'table',2:'erasure'}[kind]
                    counts['new_only_'+name] += 1
                    if not match(events[b'S'], msg, tick+STOCK_OFFSET):
                        counts['new_only_'+name+'_beyond_stock'] += 1
                        if prior_address(addresses, msg, tick+STOCK_OFFSET):
                            counts['new_only_'+name+'_prior_stock'] += 1
                    if not match(events[b'U'], msg, tick+STOCK_OFFSET):
                        counts['new_only_'+name+'_beyond_unified'] += 1
                totals.update(counts)
                output.write(json.dumps({'second': processed, 'counts': counts,
                                         'old_only_missed_rows': missed_original})+'\n')
                processed += 1
                del samples[:RATE*2]
                first += RATE
                if processed % 100 == 0:
                    output.flush()
                    print(json.dumps({'processed': processed, 'totals': totals}), flush=True)
                if args.limit_seconds and processed >= args.limit_seconds:
                    break
            if args.limit_seconds and processed >= args.limit_seconds:
                break
    summary = {'processed_seconds': processed, 'counts': dict(totals),
               'stock_bitmap_sightings': bitmap_index}
    args.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
