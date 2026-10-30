class LRUCache:
    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity, self.values, self.used, self.tick = capacity, {}, {}, 0

    def _touch(self, key):
        self.tick += 1
        self.used[key] = self.tick

    def get(self, key):
        if key not in self.values:
            return None
        self._touch(key)
        return self.values[key]

    def put(self, key, value):
        self.values[key] = value
        self._touch(key)
        if len(self.values) > self.capacity:
            oldest = min(self.used, key=self.used.get)  # ponytail: O(n) eviction scan, heap if capacity grows
            del self.values[oldest], self.used[oldest]
