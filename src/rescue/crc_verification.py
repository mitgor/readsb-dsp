"""Quarantined Broad CRC RF evidence, sampled into a bounded 12-hour archive.

The collector never publishes to the feeder. A ten-second delay attaches later
stock observations to a candidate without treating them as a training label.
"""
import bisect
import time
from collections import Counter, deque
from pathlib import Path

from .telemetry import Archive

RATE = 2400000
WINDOW = 2400  # 1 ms on either side of the candidate, at 2.4 MS/s.
FOLLOWUP_S = 10


class CrcVerifier:
    def __init__(self, directory, *, lock_memory=True):
        self.archive = Archive(Path(directory), ram_limit=48*1024**2,
                               disk_limit=512*1024**2, interval=43200,
                               lock_memory=lock_memory)
        self.pending = deque()
        self.count = Counter()

    def collect(self, event, raw, epoch, first, wall, distance, age, gain_db):
        # Keep the exact 4 MS/s detector position. Rounding it to a native
        # 2.4 MS/s sample can move the replay by one 4 MS/s sample.
        delta_ticks = event['ticks'] - first*5
        if delta_ticks % 3:
            self.count['unaligned_event_clock'] += 1
            return
        sample4 = delta_ticks//3
        sample = round(delta_ticks/5)
        lo = sample-WINDOW
        lo -= lo % 3  # Preserve the original 5:3 resampler phase.
        hi = lo+2*WINDOW
        if lo < 0 or hi > len(raw)//2:
            self.count['waveform_unavailable'] += 1
            return
        record = {'record': 'training_window', 'schema_version': 3,
                  'collector': 'broad-crc-verification-v1',
                  'label_provenance': f'broad_crc_{len(event.get("flipped_bits", []))}bit_unverified',
                  'training_eligible': False, 'verification_only': True,
                  'target_hex': event['message_hex'], 'flipped_bits': event.get('flipped_bits', []),
                  'flip_confidences': event.get('flip_confidences', []),
                  'preamble_score': event.get('preamble_score'),
                  'sample_rate': RATE, 'format': 'uc8', 'sample_start': first+lo,
                  'event_sample_in_window': sample-lo,
                  'event_sample_4msps_in_window': sample4-lo*5//3, 'epoch': epoch,
                  'unix': wall+lo/RATE, 'event_unix': wall+sample/RATE,
                  'event_ticks': event['ticks'], 'distance_nm': distance,
                  'position_age_s': age, 'gain_db': gain_db}
        self.pending.append((record, bytes(raw[2*lo:2*hi])))
        self.count['offered'] += 1
        if len(self.pending) > 2000:
            self.pending.popleft()
            self.count['pending_overflow'] += 1

    def settle(self, frames, epoch, wall):
        """Observe a later stock-only window; no candidate can confirm itself."""
        while self.pending and self.pending[0][0]['event_unix'] + FOLLOWUP_S <= wall:
            record, snippet = self.pending.popleft()
            if record['epoch'] != epoch:
                self.count['epoch_changed'] += 1
                continue
            tick = record['event_ticks']
            icao = record['target_hex'][2:8]
            if hasattr(frames, 'identities'):
                rows = frames.identities.get(icao, ())
            else:
                rows = sorted((f['ticks'], f['message_hex']) for f in frames
                              if f['message_hex'][2:8] == icao)
            lo = bisect.bisect_right(rows, (tick, '\uffff'))
            prior = [(t, p) for t, p in rows[max(0, lo-32):lo]
                     if t >= tick - FOLLOWUP_S*12000000][-16:]
            future_all = [(t, p) for t, p in rows[lo:]
                          if t <= tick + FOLLOWUP_S*12000000]
            future = future_all[:16]
            record['stock_prior'] = [{'ticks': t, 'message_hex': p} for t, p in prior]
            record['stock_followup'] = [{'ticks': t, 'message_hex': p} for t, p in future]
            record['future_stock_same_icao'] = len(future_all)
            record['future_stock_exact_payload'] = sum(p == record['target_hex'] for _, p in future_all)
            record['future_stock_observation_complete'] = True
            if self.archive.add(record, snippet):
                self.count['retained'] += 1
            else:
                self.count['archive_skipped'] += 1

    def flush(self, status=None, *, force=False):
        return self.archive.flush(status or self.report(), force=force)

    def close(self):
        while self.pending:
            record, snippet = self.pending.popleft()
            record['future_stock_observation_complete'] = False
            if self.archive.add(record, snippet):
                self.count['retained_incomplete_followup'] += 1
            else:
                self.count['archive_skipped'] += 1
        return self.flush(force=True)

    def report(self):
        return {'enabled': True, 'pending': len(self.pending), 'counts': dict(self.count),
                'archive': self.archive.report(),
                'policy': 'Research-only; 10-second stock follow-up; 1 ms RF context; '
                          '128-record reservoir per flip-count/distance stratum; 12-hour bulk writes'}
