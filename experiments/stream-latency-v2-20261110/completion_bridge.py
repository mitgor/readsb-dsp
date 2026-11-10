"""Event-driven, bounded admission bridge for isolated saved-RF experiments.

No sockets, SDR ownership, production configuration or background polling. Call
``offer`` for completed producer work and ``on_stock`` (or ``notify_stock`` when
an external owner appends the native admission index), then ``drain``. Repeated
``drain`` calls without new evidence do no work.
"""
from collections import Counter, OrderedDict, deque

from rescue.shadow import evaluate as production_evaluate
from rescue.stock_history import StockSnapshot
from rescue.stream1090_shadow import compare, valid_df17


class EvidenceRetry:
    """Retry alignment-pending slices once per changed causal evidence revision."""
    def __init__(self):
        self.attempted = {}

    def select(self, window, pending, evidence_end_tick, revision, now_s):
        result = []
        for index, (_lo, hi) in pending.items():
            key = window, index
            if hi <= evidence_end_tick and self.attempted.get(key) != revision:
                self.attempted[key] = revision
                result.append(index)
        return result

    def resolved(self, window, index):
        self.attempted.pop((window, index), None)

    def close(self, window):
        for key in [key for key in self.attempted if key[0] == window]:
            del self.attempted[key]


def _evaluate_python(frames, candidates, start, stop):
    # Exact immutable projection: production evaluate can query only these keys.
    if not isinstance(frames, StockSnapshot):
        return production_evaluate(frames, candidates, start, stop)
    payloads = {r['message_hex'] for r in candidates}
    identities = {p[2:8] for p in payloads}
    view = StockSnapshot((),
        {p: frames.payloads[p] for p in payloads if p in frames.payloads},
        {i: frames.identities[i] for i in identities if i in frames.identities})
    return production_evaluate(view, candidates, start, stop)


class Bridge:
    """Two-producer completion bridge; all output still needs the final dedup.

    ``emit(row, alignment_audit, now_s, lane)`` is the sole output callback.
    ``admission`` optionally owns the Rust stock index and exposes evaluate and
    append_stock. The caller still supplies the causal StockSnapshot to drain for
    existing native clock calibration. Append stock exactly once: use on_stock,
    or append externally and notify_stock, never both.
    """
    def __init__(self, epoch, emit, admission=None, retry=None, early=True,
                 max_windows=16, max_rows_per_window=16384):
        if type(epoch) is not int or epoch < 0:
            raise ValueError('Nonnegative integer epoch required')
        if not 1 <= max_windows <= 128 or not 1 <= max_rows_per_window <= 65536:
            raise ValueError('Invalid bridge bound')
        self.epoch = epoch
        self.emit = emit
        self.admission = admission
        self.retry = retry if retry is not None else EvidenceRetry()
        self.early = early
        self.max_windows = max_windows
        self.max_rows_per_window = max_rows_per_window
        self.windows = OrderedDict()
        self.count = Counter()
        self.energy = {}
        self._dirty = deque()
        self._dirty_keys = set()
        self._stock_revision = 0
        self._energy_revision = 0
        self._last_stock_watermark = None

    def _mark(self, key):
        if key not in self._dirty_keys:
            self._dirty.append(key)
            self._dirty_keys.add(key)

    def begin(self, key, case):
        if key in self.windows:
            raise ValueError('Repeated logical window')
        if type(case.get('first')) is not int or case['first'] < 0:
            raise ValueError('Integer logical first sample required')
        if 'epoch' in case and case['epoch'] != self.epoch:
            raise ValueError('Wrong logical-window epoch')
        # Preserve finalization rows for inspection until space is needed, but
        # never evict an active or pending window to conceal missing work.
        while len(self.windows) >= self.max_windows:
            old = next((k for k, w in self.windows.items() if w['finalized']), None)
            if old is None:
                raise BufferError('Active logical-window cap exceeded')
            del self.windows[old]
        start = (case['first'] + 600) * 5
        self.windows[key] = dict(case=dict(case), start=start, end=start+12000000,
            native=[], energy=[], native_watermark=-1, energy_watermark=-1,
            native_done=False, energy_done=False, offset=None, next_slice=0,
            pending={}, finalized=False, native_revision=0, clock_signature=None,
            clock_result=None)

    def offer(self, key, source, epoch, rows, watermark, done):
        rows = list(rows)
        if epoch != self.epoch:
            self.count['wrong_epoch'] += len(rows)
            return
        if source not in ('native', 'energy'):
            raise ValueError('Unknown producer')
        if key not in self.windows:
            raise KeyError('Unknown logical window')
        w = self.windows[key]
        if w['finalized']:
            self.count['late_result'] += len(rows)
            return
        if type(watermark) is not int or watermark < w[source+'_watermark']:
            raise ValueError('Non-integer or backwards producer watermark')
        if w[source+'_done']:
            raise ValueError('Producer already closed')
        if len(w[source]) + len(rows) > self.max_rows_per_window:
            raise BufferError('Producer result cap exceeded')
        for row in rows:
            tick, message = row if source == 'native' else (row['ticks'], row['message_hex'])
            if type(tick) is not int or not valid_df17(message):
                raise ValueError('Invalid CRC candidate')
            if source == 'energy' and (row.get('source') != 'energy' or not w['start'] <= tick < w['end']):
                raise ValueError('Energy row outside owned logical core')
        w[source].extend(rows)
        w[source+'_watermark'] = watermark
        w[source+'_done'] = bool(done)
        if source == 'native':
            w['native_revision'] += 1
        else:
            for row in rows:
                self.energy[row['ticks'], row['message_hex']] = row
            self._energy_revision += 1
            # A newly arrived completion may rescue an older cold-start slice.
            for other, state in self.windows.items():
                if state['pending'] and not state['finalized']:
                    self._mark(other)
            # Only a one-second energy history is queried by early admission.
            # Keep four RF seconds for delayed pending windows; finalization
            # separately owns each window's complete energy rows.
            floor = watermark - 48000000
            if len(self.energy) > self.max_rows_per_window:
                self.energy = {k: v for k, v in self.energy.items() if k[0] >= floor}
            if len(self.energy) > self.max_rows_per_window*self.max_windows:
                raise BufferError('Energy evidence cap exceeded')
        self.count['producer_completions_'+source] += 1
        self._mark(key)

    def on_stock(self, frame, epoch=None):
        if epoch is not None and epoch != self.epoch:
            self.count['wrong_stock_epoch'] += 1
            return
        if self.admission is not None:
            self.admission.append_stock(frame)
        self.notify_stock()

    def notify_stock(self):
        self._stock_revision += 1
        # Bounded event subscribers, not a wall-clock sweep of historical rows.
        for key, w in self.windows.items():
            if not w['finalized'] and (w['native'] or w['energy']):
                self._mark(key)

    def _clock(self, w, frames, final=False):
        if w['offset'] is not None and not final:
            return True, ()
        signature = w['native_revision'], self._stock_revision, final
        if signature == w['clock_signature']:
            return w['clock_result']
        if hasattr(frames, 'payloads'):
            messages = {m for _, m in w['native']}
            stock = [(t, p) for p in messages for t in frames.payloads.get(p, ())
                     if w['start']-60000 <= t < w['end']+60000]
        else:
            stock = [(r['ticks'], r['message_hex']) for r in frames
                     if w['start']-60000 <= r['ticks'] < w['end']+60000]
        self.count['clock_evaluations'] += 1
        audit, extras = compare(w['native'], stock)
        result = None
        if audit['aligned']:
            if w['offset'] is None:
                w['offset'] = audit['offset_ticks']
                self.count['clock_ready'] += 1
            elif abs(w['offset']-audit['offset_ticks']) > 24:
                self.count['clock_shift_after_ready'] += 1
                raise RuntimeError('Logical-window clock shifted after early publication')
            result = audit, extras
        w['clock_signature'], w['clock_result'] = signature, result
        return result

    def _evaluate(self, frames, candidates, lo, hi):
        self.count['admission_calls'] += 1
        if self.admission is not None:
            return self.admission.evaluate(candidates, lo, hi)
        return _evaluate_python(frames, candidates, lo, hi)

    def _publish(self, rows, audit, lo, hi, now, lane):
        for row in rows:
            if lo <= row['ticks'] < hi:
                self.emit(row, audit, now, lane)
                self.count['publication_attempts_'+lane] += 1

    def drain(self, frames, stock_watermark, now):
        if stock_watermark is None:
            return
        if type(stock_watermark) is not int:
            raise ValueError('Integer stock watermark required')
        if self._last_stock_watermark != stock_watermark:
            self._last_stock_watermark = stock_watermark
            self.notify_stock()
        # Process this event generation once. Unchanged calls are constant work.
        keys = list(self._dirty)
        self._dirty.clear()
        self._dirty_keys.clear()
        for key in keys:
            w = self.windows.get(key)
            if w is None or w['finalized']:
                continue
            self.count['dirty_window_visits'] += 1
            final_ready = w['native_done'] and w['energy_done'] and stock_watermark >= w['end']+1440
            evidence_end = min(w['native_watermark'], w['energy_watermark'], stock_watermark)-1440
            if self.early:
                while w['next_slice'] < 50:
                    index = w['next_slice']
                    lo = w['start']+index*240000
                    hi = min(w['end'], lo+240000)
                    if hi > evidence_end:
                        break
                    w['pending'][index] = lo, hi
                    w['next_slice'] += 1
            if self.early and w['pending'] and self._clock(w, frames):
                # RF-later anchors may help a waiting older packet only once
                # their completion has actually arrived. No future completion
                # or stock snapshot is consulted.
                anchors = [r for r in self.energy.values()
                           if evidence_end-12000000 <= r['ticks'] < evidence_end]
                revision = self._stock_revision, self._energy_revision, w['native_revision']
                selected = self.retry.select(key, w['pending'], evidence_end, revision, now)
                for index in selected:
                    lo, hi = w['pending'][index]
                    events = [dict(source='stream1090', ticks=t+w['offset'], message_hex=m)
                              for t, m in w['native'] if lo <= t+w['offset'] < hi]
                    if not events and not any(lo <= r['ticks'] < hi for r in anchors):
                        del w['pending'][index]
                        self.retry.resolved(key, index)
                        self.count['empty_slices'] += 1
                        continue
                    out, audit, decisions = self._evaluate(frames, anchors+events, lo, hi)
                    if audit['verified']:
                        self.count.update(decisions)
                        self._publish(out, audit, lo, hi, now, 'early')
                        del w['pending'][index]
                        self.retry.resolved(key, index)
                        self.count['resolved_slices'] += 1
                    else:
                        self.count['early_alignment_not_ready'] += 1
            if final_ready:
                clock = self._clock(w, frames, final=True)
                if clock:
                    native = [dict(source='stream1090', ticks=t, message_hex=m)
                              for t, m in clock[1] if w['start'] <= t < w['end']]
                    out, audit, decisions = self._evaluate(frames, w['energy']+native, w['start'], w['end'])
                    self.count.update({'final_'+k: v for k, v in decisions.items()})
                    if audit['verified']:
                        self._publish(out, audit, w['start'], w['end'], now, 'final')
                    else:
                        self.count['final_alignment_not_ready'] += 1
                else:
                    self.count['final_clock_not_ready'] += 1
                w['finalized'] = True
                w['pending'].clear()
                self.retry.close(key)
                self.count['finalized_windows'] += 1

    def pending(self):
        return sum(not w['finalized'] for w in self.windows.values())
