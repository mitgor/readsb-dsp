"""Optional coordinator index. Caller owns synchronization, as for LiveInput.frames.

Arrival-order eviction and sample-clock order are deliberately separate. Snapshots
own tuples: later input/eviction cannot change an admission decision mid-window.
"""
from bisect import bisect_left, bisect_right, insort
from collections import deque
from collections.abc import Sequence
from types import MappingProxyType


class StockSnapshot(Sequence):
    def __init__(self, frames, payloads, identities):
        self.frames = tuple(frames)
        self.payloads = MappingProxyType(payloads)
        self.identities = MappingProxyType(identities)

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, key):
        return self.frames[key]

    def __iter__(self):
        return iter(self.frames)


class StockHistory:
    def __init__(self, maxlen=100000):
        if maxlen < 1:
            raise ValueError('positive history capacity required')
        self.maxlen = maxlen
        self.frames = deque()
        self.payloads = {}
        self.identities = {}
        self.dirty_payloads = set()
        self.dirty_identities = set()
        self.frozen_payloads = {}
        self.frozen_identities = {}
        self.cached = None

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, key):
        return self.frames[key]

    def append(self, frame):
        if len(self.frames) == self.maxlen:
            self.popleft()
        # Own the row, matching snapshot isolation for incoming caller dictionaries.
        frame = dict(frame)
        self.frames.append(frame)
        p, t = frame['message_hex'], frame['ticks']
        insort(self.payloads.setdefault(p, []), t)
        insort(self.identities.setdefault(p[2:8], []), (t, p))
        self._dirty(p)

    def popleft(self):
        frame = self.frames.popleft()
        p, t = frame['message_hex'], frame['ticks']
        for mapping, key, value in ((self.payloads, p, t),
                                    (self.identities, p[2:8], (t, p))):
            rows = mapping[key]
            rows.pop(bisect_left(rows, value))
            if not rows:
                del mapping[key]
        self._dirty(p)
        return frame

    def _dirty(self, payload):
        for live,frozen,dirty,key in ((self.payloads,self.frozen_payloads,self.dirty_payloads,payload),
                                       (self.identities,self.frozen_identities,self.dirty_identities,payload[2:8])):
            if key in live or key in frozen:
                dirty.add(key)
            else:
                dirty.discard(key)
        self.cached = None

    def snapshot(self):
        if self.cached is None:
            # Only changed keys need tuple materialization. Dictionaries are copied
            # once per snapshot; previous snapshots never alias mutable lists/maps.
            for live, frozen, dirty in ((self.payloads, self.frozen_payloads, self.dirty_payloads),
                                        (self.identities, self.frozen_identities, self.dirty_identities)):
                for key in dirty:
                    if key in live:
                        frozen[key] = tuple(live[key])
                    else:
                        frozen.pop(key, None)
                dirty.clear()
            self.cached = StockSnapshot(self.frames, dict(self.frozen_payloads),
                                        dict(self.frozen_identities))
        return self.cached


def has_prior(rows, ticks):
    i = bisect_right(rows, (ticks, chr(0x10ffff)))
    return i > 0 and rows[i - 1][0] >= ticks - 360000000


def has_conflict(rows, ticks, payload):
    i = bisect_left(rows, (ticks - 48, ''))
    while i < len(rows) and rows[i][0] <= ticks + 48:
        if rows[i][1] != payload:
            return True
        i += 1
    return False
