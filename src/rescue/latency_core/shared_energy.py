"""Isolated in-memory fan-out of completed, pre-admission energy candidates.

This module never decodes RF, opens a socket, accesses production files, creates
stock identities, or deduplicates energy candidates. The existing downstream
admission function remains responsible for CRC/alignment/identity/conflict checks.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import heapq
import math
import time
from types import MappingProxyType
from typing import Callable, Hashable, Mapping

COVERAGE = 'all_valid_energy_before_admission'


def _integer(value, name):
    if type(value) is not int:
        raise ValueError(name + ' must be an integer')
    return value


def _time(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(name + ' must be finite and nonnegative')
    return float(value)


@dataclass(frozen=True)
class EnergyCompletion:
    """One fully completed upstream block and its exclusive RF ownership.

    ``available_s`` is the actual completion/receipt time on the consumer replay
    clock, not the RF block end or a fitted timestamp. ``observed_through_tick``
    describes RF that was available to that upstream job. A watermark can lag
    decoded candidates: it is conservative *coverage*, not the last output tick.
    ``producer_id`` uniquely identifies the original upstream computation.
    """
    epoch: int
    window: Hashable
    sequence: int
    start_tick: int
    end_tick: int
    observed_through_tick: int
    watermark: int
    available_s: float
    rows: tuple[Mapping, ...]
    done: bool
    producer_id: str
    producer_cpu_s: float
    coverage: str = COVERAGE


class EnergyAccounting:
    """Share one ledger between consumers to count upstream work only once."""
    def __init__(self, max_jobs=100000):
        if type(max_jobs) is not int or max_jobs < 1:
            raise ValueError('Positive accounting capacity required')
        self.max_jobs = max_jobs
        self._producer = {}
        self.adapter_cpu_s = 0.0

    def record(self, producer_id, cpu_s):
        cpu_s = _time(cpu_s, 'producer_cpu_s')
        previous = self._producer.get(producer_id)
        if producer_id not in self._producer and len(self._producer) >= self.max_jobs:
            raise OverflowError('Energy accounting session cap; close the finite session')
        if previous is not None and previous != cpu_s:
            raise ValueError('Conflicting CPU receipt for the same producer job')
        self._producer[producer_id] = cpu_s

    def summary(self, rf_seconds=None):
        result = {
            'unique_upstream_jobs': len(self._producer),
            'upstream_cpu_s_counted_once': sum(self._producer.values()),
            'adapter_cpu_s': self.adapter_cpu_s,
            'duplicate_energy_decodes_by_adapter': 0,
            'scope': 'Upstream energy cost counted once, plus measured adapter work; downstream decoder/admission CPU must be added separately. No live sharing or total-system saving is claimed.',
        }
        if rf_seconds is not None:
            rf_seconds = _time(rf_seconds, 'rf_seconds')
            if not rf_seconds:
                raise ValueError('rf_seconds must be positive')
            result['upstream_cpu_s_per_RF_s'] = result['upstream_cpu_s_counted_once'] / rf_seconds
            result['adapter_cpu_s_per_RF_s'] = self.adapter_cpu_s / rf_seconds
        return result


@dataclass
class _Window:
    start: int
    end: int
    sequence: int = 0
    next_tick: int = 0
    watermark: int | None = None
    available: float = 0.0
    closed: bool = False
    delivered_sequence: int = 0


class SharedEnergyFeed:
    """Bounded causal adapter; callback has exactly the old ``Bridge.offer`` API.

    ``submit`` accepts only already-completed input. ``queue_replay`` is an
    explicit test-only path for loading recorded *complete producer output*;
    future records stay quarantined in the heap until ``release(now_s)``.
    Never use the old accepted-extras-only production journal as this input.
    """
    def __init__(self, epoch, emit: Callable, *, replay=False, accounting=None,
                 max_pending=512, max_rows=100000, max_windows=16):
        self.epoch = _integer(epoch, 'epoch')
        if min(max_pending, max_rows, max_windows) < 1:
            raise ValueError('Positive bounds required')
        self.emit = emit
        self.replay = bool(replay)
        self.accounting = accounting if accounting is not None else EnergyAccounting()
        self.max_pending, self.max_rows, self.max_windows = max_pending, max_rows, max_windows
        self.windows = {}
        self.closed = deque(maxlen=max_windows * 2)
        self.pending = []
        self.pending_rows = 0
        self.serial = 0
        self.now = 0.0
        self.count = Counter()

    def begin(self, window, start_tick, end_tick):
        hash(window)
        start_tick = _integer(start_tick, 'start_tick')
        end_tick = _integer(end_tick, 'end_tick')
        if start_tick >= end_tick or window in self.windows or window in self.closed:
            raise ValueError('Invalid/repeated logical window')
        if len(self.windows) >= self.max_windows:
            raise OverflowError('Shared energy window cap')
        self.windows[window] = _Window(start_tick, end_tick, next_tick=start_tick)

    def begin_case(self, window, case):
        """Register the unchanged one-second core with its 600-sample halo."""
        first = _integer(case['first'], 'first')
        self.begin(window, (first + 600) * 5, (first + 600 + 2400000) * 5)

    def _enqueue(self, completion):
        c = completion
        if not isinstance(c, EnergyCompletion):
            raise TypeError('Expected a complete EnergyCompletion receipt')
        _integer(c.epoch, 'epoch')
        if c.epoch != self.epoch:
            self.count['wrong_epoch'] += 1
            raise ValueError('Wrong RF epoch')
        if c.coverage != COVERAGE:
            raise ValueError('Complete pre-admission energy candidates required, not accepted extras')
        if c.window not in self.windows:
            raise ValueError('Unknown/closed window')
        w = self.windows[c.window]
        for name in ['sequence', 'start_tick', 'end_tick', 'observed_through_tick', 'watermark']:
            _integer(getattr(c, name), name)
        available = _time(c.available_s, 'available_s')
        cpu = _time(c.producer_cpu_s, 'producer_cpu_s')
        if not c.producer_id or not isinstance(c.producer_id, str) or type(c.done) is not bool:
            raise ValueError('Explicit producer identity and terminal flag required')
        if w.closed or c.sequence != w.sequence or c.start_tick != w.next_tick:
            raise ValueError('Repeated, overlapping or gapped energy completion')
        if not c.start_tick < c.end_tick <= w.end or c.end_tick > c.observed_through_tick:
            raise ValueError('Ownership outside captured RF')
        if c.watermark > c.observed_through_tick or (w.watermark is not None and c.watermark < w.watermark):
            raise ValueError('Impossible/regressing RF watermark')
        if available < w.available:
            raise ValueError('Per-window completion clock regressed')
        if c.done != (c.end_tick == w.end):
            raise ValueError('Terminal completion must close the exact logical core')
        if len(self.pending) >= self.max_pending or self.pending_rows + len(c.rows) > self.max_rows:
            raise OverflowError('Shared energy pending RAM cap')
        frozen = []
        for row in c.rows:
            if row.get('source') != 'energy':
                raise ValueError('Only original energy candidates are accepted')
            ticks = _integer(row.get('ticks'), 'candidate tick')
            payload = row.get('message_hex')
            if not c.start_tick <= ticks < c.end_tick:
                raise ValueError('Candidate outside exclusive owned RF block')
            if not isinstance(payload, str) or len(payload) != 28:
                raise ValueError('Expected 112-bit candidate payload')
            try:
                raw = bytes.fromhex(payload)
            except ValueError:
                raise ValueError('Invalid hexadecimal payload') from None
            if len(raw) != 14 or raw[0] >> 3 != 17:
                raise ValueError('Expected DF17 energy candidate')
            # These are the only fields the admission guard reads. No nested
            # caller-owned metadata is retained and caller mutation cannot leak.
            frozen.append(MappingProxyType(dict(source='energy', ticks=ticks, message_hex=payload)))
        self.accounting.record(c.producer_id, cpu)
        self.serial += 1
        receipt = EnergyCompletion(c.epoch, c.window, c.sequence, c.start_tick,
                                   c.end_tick, c.observed_through_tick, c.watermark,
                                   available, tuple(frozen), c.done, c.producer_id,
                                   cpu, c.coverage)
        heapq.heappush(self.pending, (available, self.serial, receipt))
        self.pending_rows += len(frozen)
        w.sequence += 1
        w.next_tick = c.end_tick
        w.watermark = c.watermark
        w.available = available
        w.closed = c.done
        self.count['queued_completions'] += 1

    def submit(self, completion, now_s):
        """Production-shaped ingestion: cannot claim a future completion."""
        started = time.thread_time()
        try:
            now_s = _time(now_s, 'now_s')
            if now_s < self.now or completion.available_s > now_s:
                raise ValueError('Energy completion is not causally available')
            self._enqueue(completion)
        finally:
            self.accounting.adapter_cpu_s += time.thread_time() - started
        return self.release(now_s)

    def queue_replay(self, completion):
        if not self.replay:
            raise ValueError('Recorded future scheduling requires explicit replay mode')
        started = time.thread_time()
        try:
            self._enqueue(completion)
        finally:
            self.accounting.adapter_cpu_s += time.thread_time() - started

    def release(self, now_s):
        started = time.thread_time()
        try:
            now_s = _time(now_s, 'now_s')
            if now_s < self.now:
                raise ValueError('Consumer clock regressed')
            self.now = now_s
            released = 0
            while self.pending and self.pending[0][0] <= now_s:
                _, _, c = self.pending[0]
                w = self.windows[c.window]
                if c.sequence != w.delivered_sequence:
                    raise RuntimeError('Completion order corrupted')
                self.emit(c.window, 'energy', c.epoch,
                          [dict(row) for row in c.rows], c.watermark, c.done)
                heapq.heappop(self.pending)
                self.pending_rows -= len(c.rows)
                w.delivered_sequence += 1
                released += 1
                self.count['delivered_completions'] += 1
                self.count['delivered_rows'] += len(c.rows)
                if c.done:
                    self.closed.append(c.window)
                    del self.windows[c.window]
            return released
        finally:
            self.accounting.adapter_cpu_s += time.thread_time() - started


def completion_from_block(*, epoch, window, index, first, total_samples, stop,
                          rows, available_s, producer_cpu_s, producer_id=None):
    """Adapt the previous benchmark's unchanged 50 ms producer callback.

    ``rows`` must contain all CRC-valid energy candidates for this completed
    block, before stock/admission filtering. This helper owns the original core
    and removes only halo rows, never stock duplicates or possible anchors.
    """
    if index < 0 or stop != min(total_samples, (index + 1) * 120000):
        raise ValueError('Expected the frozen contiguous 50 ms block schedule')
    start = index * 120000
    core_start, core_end = (first + 600) * 5, (first + 600 + 2400000) * 5
    own_start = max(core_start, (first + start) * 5)
    own_end = min(core_end, (first + stop) * 5)
    done = stop == total_samples
    observed = (first + min(total_samples, stop + 600)) * 5
    watermark = core_end + 1440 if done else (first + stop) * 5 - 6000
    owned = tuple(dict(r) for r in rows if own_start <= r['ticks'] < own_end)
    return EnergyCompletion(epoch, window, index, own_start, own_end, observed,
                            watermark, available_s, owned, done,
                            producer_id or f'energy:{epoch}:{window}:{index}',
                            producer_cpu_s)
