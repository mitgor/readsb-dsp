"""Offline-only bounded acquisition retry. No registration in the live pipeline.

Keep the original decoder first. Revisit +/- one 4 Msps sample around unresolved
preamble peaks, allowing a shifted energy header to pass the ordinary DF17 gate.
No header forcing, CRC bit repair, joint fitting, RF mutation, or output sockets.
"""
import numpy as np
from .native import header_ids
from .coherent_fast import native_windows
from .dsp import PREAMBLE, payloads, crc_batch

BUDGET = 8

def retry(iq, core, offset, backend, baseline):
    starts, score = backend.coherent_scores(iq, core, .35)
    starts = starts[(starts >= 9) & (starts + 489 < len(iq))]
    if not len(starts): return [], {'windows': 0}
    p = np.abs(iq[starts[:,None] + np.arange(32)])**2
    rank = p[:,PREAMBLE.astype(bool)].mean(1)/(p[:,~PREAMBLE.astype(bool)].mean(1)+1e-8)
    chosen = []
    occupied = [r['sample_4msps']-offset for r in baseline if r['source'] != 'broad_crc']
    for s in starts[np.argsort(-rank, kind='stable')]:
        if any(abs(int(s)-t) <= 2 for t in occupied): continue
        neighbors = np.array([s-1,s+1], np.int64)
        neighbors = neighbors[header_ids(iq, neighbors)]
        for t in neighbors:
            if int(t) not in chosen: chosen.append(int(t))
            if len(chosen) == BUDGET: break
        if len(chosen) == BUDGET: break
    if not chosen: return [], {'windows': 0}
    positions = np.asarray(chosen, np.int64)
    result = native_windows(iq, positions)
    rows = payloads(result[0])
    valid = (crc_batch(rows) == 0) & (rows[:,0] >> 3 == 17)
    events = [dict(sample_4msps=float(offset+positions[j]),seconds=float(offset+positions[j])/4e6,
                   message_hex=rows[j].tobytes().hex(),source='coherent',research_method='bounded_timing_retry',
                   raw_crc_valid=True,training_eligible=False) for j in np.flatnonzero(valid)]
    return events, {'windows': len(chosen)}
