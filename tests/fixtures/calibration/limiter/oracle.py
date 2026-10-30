"""Calibration oracle: candidate.Limiter against a sliding log over the half-open window (now - window, now]."""
import random

from candidate import Limiter


class Model:
    def __init__(self, limit, window):
        self.limit, self.window, self.log = limit, window, {}

    def allow(self, key, now):
        log = [t for t in self.log.get(key, []) if t > now - self.window]
        allowed = len(log) < self.limit
        if allowed:
            log.append(now)
        self.log[key] = log
        return allowed


def check(limit, window, calls):
    limiter, model = Limiter(limit, window), Model(limit, window)
    for key, now in calls:
        assert limiter.allow(key, now) == model.allow(key, now), (limit, window, calls)


check(2, 10, [("k", 5), ("k", 5), ("k", 10), ("k", 14), ("k", 15), ("k", 15)])  # no reset at window edges
check(1, 10, [("k", 0), ("k", 9), ("k", 10), ("j", 10)])  # an event exactly `window` old has expired
rng = random.Random(4007)
for _ in range(200):
    now, calls = 0, []
    for _ in range(40):
        now += rng.randint(0, 3)
        calls.append((rng.randint(0, 2), now))
    check(rng.randint(1, 3), rng.randint(1, 5), calls)
