from bisect import bisect_right


class Limiter:
    def __init__(self, limit, window):
        self.limit, self.window, self.log = limit, window, {}

    def allow(self, key, now):
        log = self.log.setdefault(key, [])  # ponytail: log never pruned, prune when memory matters
        if len(log) - bisect_right(log, now - self.window) >= self.limit:
            return False
        log.append(now)
        return True
