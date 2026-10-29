#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Local-file integration controls; never opens a receiver or network port.

Requires NumPy for generated fixtures only. Optional --capture is UC8 at 2.4MS/s.
Raw inputs/output stay in the caller's temporary directory, not source control.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

import numpy as np

PATTERN = re.compile(rb'@([0-9a-fA-F]{12})([0-9a-fA-F]+);')
EXAMPLE = bytes.fromhex('8d40621d58c382d690c8ac2863a7')


def run(exe, path, options):
    start = time.monotonic()
    proc = subprocess.run([str(exe), '--device-type', 'ifile', '--ifile', str(path),
                           '--iformat', 'UC8', '--raw', '--mlat', *options],
                          capture_output=True, timeout=60)
    records = Counter((int(t, 16), m.lower()) for t, m in PATTERN.findall(proc.stdout))
    summary = re.search(rb'DSP rescue summary: (.*)', proc.stderr)
    # Upstream ifile currently exits 1 at EOF. Require actual records/summary below.
    assert proc.returncode in (0, 1), proc.stderr.decode(errors='replace')
    result = {'exit': proc.returncode, 'wall_s': time.monotonic()-start,
              'records': sum(records.values()),
              'df17': sum(n for (_, m), n in records.items() if int(m[:2], 16) >> 3 == 17)}
    if summary:
        result['rescue'] = json.loads(summary[1])
    return records, result


def compare(exe, stock_exe, path):
    stock, baseline = run(stock_exe, path, [])
    report = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'stock': baseline}
    for name, options in [('disabled', []), ('shadow', ['--dsp-rescue']),
                          ('phase_shadow', ['--dsp-rescue', '--dsp-rescue-stream-phase']),
                          ('phase_repair_shadow', ['--dsp-rescue', '--dsp-rescue-stream-phase',
                                                   '--dsp-rescue-stream-phase-repair']),
                          ('output', ['--dsp-rescue', '--dsp-rescue-output']),
                          ('tight_budget', ['--dsp-rescue', '--dsp-rescue-budget-us', '100'])]:
        received, r = run(exe, path, options)
        r['missing_stock_records'] = sum((stock-received).values())
        r['extra_records'] = sum((received-stock).values())
        assert not r['missing_stock_records'], (name, r)
        if name != 'output':
            assert received == stock, (name, r)
        if name != 'disabled':
            assert r['rescue']['forwarded'] == (r['extra_records'] if name == 'output' else 0)
        report[name] = r
    return report


def fixture(path):
    rng = np.random.default_rng(251025)
    raw = np.clip(np.rint(rng.normal(127.5, 1, (480000, 2))), 0, 255).astype(np.uint8)
    # Include every 12MHz subphase and starts on both sides of 65536-sample
    # SDR buffer boundaries, including packets extending across them.
    # Avoid mutual overlaps; individual boundary offsets tested across blocks.
    starts = [2000 + p*12000 + p/5 for p in range(5)] + [65536*b+(-200,-40,2,50,-120,10)[b-1] for b in range(1,7)]
    bits = np.unpackbits(np.frombuffer(EXAMPLE, np.uint8))
    for start in starts:
        lo, hi = int(start)-4, int(start)+300
        t = (np.arange(lo, hi)-start)/2.4 # microseconds
        on = np.zeros(len(t), bool)
        for pulse in (0, 1, 3.5, 4.5):
            on |= (t >= pulse) & (t < pulse+.5)
        b = np.floor(t-8).astype(int)
        valid = (b >= 0) & (b < 112)
        phase = t[valid]-8-b[valid]
        on[valid] |= np.where(bits[b[valid]], phase < .5, phase >= .5)
        raw[lo:hi, 0] = np.where(on, 210, 128).astype(np.uint8)
        raw[lo:hi, 1] = 128
    path.write_bytes(raw.tobytes())
    return len(starts)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--readsb', type=Path, default=Path('./readsb'))
    p.add_argument('--stock-readsb', type=Path, required=True)
    p.add_argument('--capture', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    exe, stock = a.readsb.resolve(), a.stock_readsb.resolve()
    report = {}
    with tempfile.TemporaryDirectory(prefix='readsb-native-dsp-') as tmp:
        tmp = Path(tmp)
        raw = tmp/'synthetic.uc8'
        report['synthetic_packets'] = fixture(raw)
        report['synthetic_boundaries'] = compare(exe, stock, raw)
        assert report['synthetic_boundaries']['stock']['df17'] == report['synthetic_packets']
        # Pure noise and shuffled real I/Q pairs are false-positive controls,
        # not proof that CRC-valid rescue candidates are independently true.
        noise = np.random.default_rng(251025).integers(0,256,(480000,2),dtype=np.uint8)
        path=tmp/'noise.uc8'; path.write_bytes(noise.tobytes())
        _, r = run(exe, path, ['--dsp-rescue', '--dsp-rescue-budget-us', '50000'])
        assert sum(r['rescue']['raw']) == 0, r
        report['noise'] = r
        if a.capture:
            report['recorded'] = compare(exe, stock, a.capture)
            pairs=np.fromfile(a.capture,dtype=np.uint8).reshape(-1,2).copy()
            np.random.default_rng(251025).shuffle(pairs)
            path=tmp/'shuffled.uc8';path.write_bytes(pairs.tobytes())
            _, r=run(exe,path,['--dsp-rescue','--dsp-rescue-budget-us','50000'])
            assert sum(r['rescue']['raw']) == 0, r
            report['shuffled'] = r
        # Reject configuration mistakes before reading from SDR/input.
        for opts in (['--dsp-rescue-output'], ['--dsp-rescue-stream-phase'],
                     ['--dsp-rescue-stream-phase-repair'],
                     ['--dsp-rescue','--dsp-rescue-stream-phase-repair'],
                     ['--dsp-rescue-budget-us','oops'],
                     ['--dsp-rescue-budget-us','0'], ['--dsp-rescue-budget-us','50001'],
                     ['--net-only','--dsp-rescue'],
                     ['--device-type','ifile','--ifile',str(raw),'--iformat','SC16','--dsp-rescue']):
            proc=subprocess.run([str(exe),*opts],capture_output=True,timeout=10)
            assert proc.returncode != 0, opts
        report['invalid_configurations_rejected']=9
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
