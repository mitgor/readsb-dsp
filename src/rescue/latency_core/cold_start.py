"""Bounded event-driven retry selection; never admits or publishes a packet.

Only the bridge's already-arrived native/energy/stock evidence revision can
trigger a retry. Wall time is diagnostic and cannot authorize a retry. CRC,
clock, stock identity, conflicts and alignment remain the admission engine's job.
"""
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass, field
import math


@dataclass
class _Window:
    revision: tuple | None = None
    evidence_end: int | None = None
    now: float = 0.0
    pending: dict = field(default_factory=dict)
    attempted: dict = field(default_factory=dict)
    resolved: set = field(default_factory=set)


class ColdStartRetry:
    """Drop-in ``Bridge(..., retry=ColdStartRetry())`` selection policy.

    ``pending`` is the bridge's complete current map of slice index to RF
    ``(lo, hi)``. Failed slices remain in that map. A later causal completion may
    supply enough anchors to admit an older slice; unchanged evidence and elapsed
    time alone never cause another attempt. Bounds fail closed, without eviction
    of active work or weakening the bridge's finalization fallback.
    """
    def __init__(self, max_windows=16, max_slices=50, max_pending=800):
        for name, value in [('max_windows', max_windows), ('max_slices', max_slices),
                            ('max_pending', max_pending)]:
            if type(value) is not int or value < 1:
                raise ValueError(name + ' must be a positive integer')
        if max_windows > 128 or max_slices > 50 or max_pending > 6400:
            raise ValueError('Retry bound exceeds the experiment contract')
        self.max_windows, self.max_slices, self.max_pending = max_windows, max_slices, max_pending
        self.windows = OrderedDict()
        self.closed = deque(maxlen=max_windows * 2)
        self.count = Counter()

    @property
    def pending_count(self):
        return sum(len(w.pending) for w in self.windows.values())

    def select(self, window, pending, evidence_end_tick, revision_tuple, now_s):
        hash(window)
        if window in self.closed:
            raise ValueError('Closed retry window; reset for a new RF epoch')
        if type(evidence_end_tick) is not int:
            raise ValueError('Integer causal evidence watermark required')
        if not isinstance(revision_tuple, tuple) or not 1 <= len(revision_tuple) <= 8:
            raise ValueError('Bounded evidence revision tuple required')
        if any(type(x) is not int or x < 0 for x in revision_tuple):
            raise ValueError('Evidence revisions must be nonnegative integers')
        if isinstance(now_s, bool) or not isinstance(now_s, (int, float)) or not math.isfinite(now_s) or now_s < 0:
            raise ValueError('Finite nonnegative completion time required')
        if not isinstance(pending, dict) or len(pending) > self.max_slices:
            raise BufferError('Pending slice bound exceeded')
        checked = {}
        for index, bounds in pending.items():
            if type(index) is not int or not 0 <= index < self.max_slices:
                raise ValueError('Invalid logical slice index')
            if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
                raise ValueError('RF slice bounds required')
            lo, hi = bounds
            if type(lo) is not int or type(hi) is not int or lo >= hi:
                raise ValueError('Nonempty integer RF slice required')
            checked[index] = (lo, hi)
        old = self.windows.get(window)
        if old is not None:
            if old.revision is not None:
                if len(revision_tuple) != len(old.revision) or any(a < b for a, b in zip(revision_tuple, old.revision)):
                    raise ValueError('Backwards evidence revision')
                if evidence_end_tick < old.evidence_end or now_s < old.now:
                    raise ValueError('Backwards causal coverage or completion time')
            for index in old.pending.keys() & checked.keys():
                if old.pending[index] != checked[index]:
                    raise ValueError('A pending slice changed RF identity')
            checked = {i: bounds for i, bounds in checked.items() if i not in old.resolved}
        if old is None and len(self.windows) >= self.max_windows:
            raise BufferError('Active retry window bound exceeded')
        total = self.pending_count - (len(old.pending) if old else 0) + len(checked)
        if total > self.max_pending:
            raise BufferError('Total pending retry bound exceeded')
        # Commit only after all checks: invalid/over-cap input cannot consume
        # state, evict older work or partially authorize candidates.
        w = old if old is not None else _Window()
        self.windows[window] = w
        w.pending = checked
        w.attempted = {i: r for i, r in w.attempted.items() if i in checked}
        result = []
        for index, (_lo, hi) in sorted(checked.items()):
            if hi > evidence_end_tick:
                self.count['waiting_for_causal_coverage'] += 1
            elif w.attempted.get(index) != revision_tuple:
                w.attempted[index] = revision_tuple
                result.append(index)
            else:
                self.count['unchanged_evidence_suppressed'] += 1
        w.revision, w.evidence_end, w.now = revision_tuple, evidence_end_tick, float(now_s)
        self.count['select_calls'] += 1
        self.count['attempts_selected'] += len(result)
        return result

    def resolved(self, window, index):
        w = self.windows.get(window)
        if w is None:
            return
        if type(index) is not int or not 0 <= index < self.max_slices:
            raise ValueError('Invalid resolved slice')
        w.pending.pop(index, None)
        w.attempted.pop(index, None)
        w.resolved.add(index)
        self.count['resolved_slices'] += 1

    def close(self, window):
        self.windows.pop(window, None)
        if window not in self.closed:
            self.closed.append(window)
        self.count['closed_windows'] += 1

    def reset(self):
        """Discard all retry state on an externally verified RF epoch change."""
        self.windows.clear()
        self.closed.clear()
        self.count['resets'] += 1
