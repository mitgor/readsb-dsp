"""Cooperative rescue-only admission. Never throttles stock, feeders or capture."""
from collections import deque
from dataclasses import asdict, dataclass
import math
from pathlib import Path
import time

PROFILES = ('full', 'bounded', 'cheap', 'energy', 'stock-only')

@dataclass(frozen=True)
class Config:
    enabled: bool = True
    target_percent: float = 55.0
    ceiling_percent: float = 60.0
    window_seconds: float = 30.0
    lower_interval_seconds: float = 5.0
    recovery_seconds: float = 60.0
    recovery_margin_percent: float = 5.0
    stop_temperature_c: float = 75.0

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError('enabled must be boolean')
        for key, value in asdict(self).items():
            if key != 'enabled' and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError('Non-finite or invalid setting: '+key)
        if not 5 <= self.target_percent < self.ceiling_percent <= 95:
            raise ValueError('Require 5 <= target < ceiling <= 95')
        if not 5 <= self.window_seconds <= 300 or not 1 <= self.lower_interval_seconds <= 60 or not 15 <= self.recovery_seconds <= 600:
            raise ValueError('Invalid averaging or control interval')
        if not 0 < self.recovery_margin_percent < self.target_percent or not 50 <= self.stop_temperature_c <= 85:
            raise ValueError('Invalid recovery margin or temperature')

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value)-set(cls.__dataclass_fields__):
            raise ValueError('Unknown CPU-budget setting')
        return cls(**value)


def read_cpu(path=Path('/proc/stat')):
    """Linux aggregate CPU ticks: guest is already included in user/nice."""
    fields = path.read_text().splitlines()[0].split()
    if fields[0] != 'cpu' or len(fields) < 5:
        raise ValueError('Missing aggregate CPU counters')
    values = [int(v) for v in fields[1:9]]
    if any(v < 0 for v in values):
        raise ValueError('Invalid CPU counters')
    return sum(values), values[3]+(values[4] if len(values)>4 else 0)


class Governor:
    def __init__(self, config=Config(), clock=time.monotonic):
        self.config, self.clock = config, clock
        self.samples = deque(maxlen=512)
        self.level = 1  # conservative during sampling warm-up
        self.changed = float('-inf')
        self.cool_since = None
        self.reason = 'warming_up'
        self.average = self.instant = None
        self.last_sample = None

    def fail(self, reason):
        self.level, self.reason = 4, reason
        self.cool_since = None
        self.changed = self.clock()
        return self.policy()

    def observe(self, total, idle, temperature=None, backlog=False, now=None):
        now = self.clock() if now is None else now
        if (type(total) is not int or type(idle) is not int or not 0 <= idle <= total
                or not math.isfinite(now) or (temperature is not None and not math.isfinite(temperature))):
            return self.fail('invalid_telemetry')
        if self.samples:
            prev = self.samples[-1]
            dt, di = total-prev[1], idle-prev[2]
            if now <= prev[0] or dt <= 0 or not 0 <= di <= dt:
                self.samples.clear()
                return self.fail('counter_reset_or_stale')
            if now-prev[0]>5:
                self.samples.clear();self.samples.append((now,total,idle));self.last_sample=now
                return self.fail('telemetry_gap')
            self.instant = 100*(dt-di)/dt
        self.samples.append((now,total,idle))
        self.last_sample = now
        while len(self.samples)>2 and self.samples[1][0] < now-self.config.window_seconds:
            self.samples.popleft()
        first=self.samples[0]; dt=total-first[1]; di=idle-first[2]
        self.average=100*(dt-di)/dt if dt else None
        if not self.config.enabled:
            self.level,self.reason=0,'disabled'
            return self.policy(now)
        if backlog or (temperature is not None and temperature>=self.config.stop_temperature_c):
            return self.fail('backlog' if backlog else 'temperature')
        if self.instant is not None and self.instant>=85:
            return self.fail('instant_cpu_emergency')
        if self.average is None or now-first[0]<3:
            self.reason='warming_up'
            return self.policy(now)
        c=self.config
        if self.average>c.target_percent:
            self.cool_since=None
            if now-self.changed>=c.lower_interval_seconds:
                self.level=min(4,self.level+(2 if self.average>c.ceiling_percent else 1))
                self.changed=now
            self.reason='cpu_ceiling' if self.average>c.ceiling_percent else 'cpu_target'
        elif self.average<c.target_percent-c.recovery_margin_percent and (temperature is None or temperature<c.stop_temperature_c-5):
            if self.cool_since is None:self.cool_since=now
            if now-self.cool_since>=c.recovery_seconds:
                self.level=max(0,self.level-1);self.changed=now;self.cool_since=now
            self.reason='slow_recovery' if self.level else 'within_budget'
        else:
            self.cool_since=None;self.reason='holding'
        return self.policy(now)

    def policy(self, now=None):
        now=self.clock() if now is None else now
        stale=self.last_sample is None or now-self.last_sample>5
        level=0 if not self.config.enabled else (4 if stale else self.level)
        return {'level':level,'profile':PROFILES[level], 'reason':'telemetry_stale' if stale and self.config.enabled else self.reason}

    def report(self):
        return {**self.policy(),'config':asdict(self.config),'total_system_cpu_percent':self.average,
                'instant_system_cpu_percent':self.instant,'scope':'total aggregate CPU; rescue-only cooperative admission',
                'guarantee':'Target, not a hard total-system cap. Stock and unrelated CPU are never throttled.'}
