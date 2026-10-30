class Limiter:
    """M1: fixed window, so a burst straddling a boundary allows up to 2 x limit."""

    def __init__(self, limit, window):
        self.limit, self.window, self.counts = limit, window, {}

    def allow(self, key, now):
        bucket = (key, now // self.window)
        if self.counts.get(bucket, 0) >= self.limit:
            return False
        self.counts[bucket] = self.counts.get(bucket, 0) + 1
        return True
