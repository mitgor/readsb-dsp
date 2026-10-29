#!/usr/bin/env python3
"""Explain Stream1090 events still missing after native repair replay."""
import argparse
from bisect import bisect_right
from collections import Counter
import json
from pathlib import Path

from analyze_stream_phase_paired import read_taps, match, prior_address, STOCK_OFFSET


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('candidates','classification','native','paired','output'):
        p.add_argument('--'+name, required=True, type=Path)
    args = p.parse_args()
    events, addresses, snapshots, chunks, chunk_times = read_taps(args.paired)
    def covered(ns):
        for source in (b'S',b'U'):
            times=chunk_times[source]; i=bisect_right(times,ns)
            if i==0 or i==len(times) or ns-times[i-1]>2_000_000_000 or times[i]-ns>2_000_000_000:
                return False
        return True
    counts=Counter()
    source_files=(args.candidates.open(),args.classification.open(),args.native.open())
    for index, lines in enumerate(zip(*source_files)):
        reference, classification, native = map(json.loads,lines)
        assert native['second']==classification['second']==index
        provenance={(tick,msg):kind for tick,msg,kind in classification['old_only_provenance_rows']}
        first,wall=reference['first_sample'],reference['wall_start_ns']
        for tick,msg in native['old_only_missed_rows']:
            kind=provenance.get((tick,msg),'unmatched')
            counts['miss_'+kind]+=1
            ns=wall+(tick-first*5)*1_000_000_000//12_000_000
            if not covered(ns):
                counts['outside_paired_coverage']+=1
                continue
            counts['paired_miss_'+kind]+=1
            if match(events[b'S'],msg,tick+STOCK_OFFSET):
                counts['in_stock_'+kind]+=1
                continue
            counts['beyond_stock_'+kind]+=1
            prior=prior_address(addresses,msg,tick+STOCK_OFFSET)
            counts['beyond_stock_'+kind+('_prior_stock' if prior else '_no_prior_stock')]+=1
    report={'counts':dict(counts)}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'counts':dict(counts)}))


if __name__=='__main__':
    main()
