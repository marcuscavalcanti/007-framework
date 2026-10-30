from collections import deque


class Limiter:
    def __init__(self, limit, window):
        self.limit, self.window, self.log = limit, window, {}

    def allow(self, key, now):
        log = self.log.setdefault(key, deque())
        while log and log[0] < now - self.window:  # M2: closed window keeps an event exactly `window` old
            log.popleft()
        if len(log) >= self.limit:
            return False
        log.append(now)
        return True
