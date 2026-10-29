#!/usr/bin/env python3
"""Check and summarize exact old-vs-native DF17 pairing on live IQ windows."""
import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status', required=True, type=Path)
    parser.add_argument('--windows', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    status = json.loads(args.status.read_text())
    windows = [json.loads(line) for line in args.windows.read_text().splitlines()]
    counts = Counter()
    offsets = []
    mads = []
    shared = []
    for row in windows:
        if not row['alignment']['aligned']:
            raise ValueError('unaligned window in paired log')
        counts.update(row['counts'])
        offsets.append(row['alignment']['offset_ticks'])
        mads.append(row['alignment']['mad_ticks'])
        shared.append(row['alignment']['shared'])
    recorded = status['counts']
    if len(windows) != recorded.get('direct_paired_rf_seconds', 0):
        raise ValueError('window count differs from status')
    for key, value in counts.items():
        if value != recorded.get('direct_'+key):
            raise ValueError(f'counter mismatch: {key}')
    old_only = counts['old_only_clean']
    beyond_stock = counts['old_only_clean_beyond_stock']
    result = {
        'source_commit': status['source_commit'],
        'old_binary': '/home/pi/stream1090-shadow/build/stream1090',
        'comparison': 'same live UC8 one-second cores; exact DF17 payload within 120 us',
        'duration_s': round(status['updated_unix']-status['started_unix'], 1),
        'paired_rf_seconds': len(windows),
        'processed_rf_seconds': recorded.get('processed_rf_seconds', 0),
        'research_iq_discontinuities': recorded.get('iq_discontinuities', 0),
        'research_queue_shed_seconds': recorded.get('shed_rf_seconds', 0),
        'old_decoder_errors': recorded.get('direct_decoder_errors', 0),
        'native_decoder_errors': recorded.get('decoder_errors', 0),
        'clock': {'median_residual_ticks': statistics.median(offsets) if offsets else None,
                  'max_mad_ticks': max(mads, default=None),
                  'min_shared_clean_frames_per_window': min(shared, default=None)},
        'counts': dict(counts),
        'old_only_clean_recovered_percent': round(100*counts['old_only_clean_recovered_by_repair']/old_only, 3) if old_only else None,
        'old_only_beyond_stock_recovered_percent': round(100*counts['old_only_clean_recovered_beyond_stock']/beyond_stock, 3) if beyond_stock else None,
        'scope_limit': ('Pinned old Stream1090 executable and native C see the same IQ. '
                        'The comparison is before the production guard and is not independent packet truth.'),
    }
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
