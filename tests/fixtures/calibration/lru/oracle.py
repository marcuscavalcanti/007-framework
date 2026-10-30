"""Calibration oracle: candidate.LRUCache against a list model (least -> most recent)."""
import random

from candidate import LRUCache


class Model:
    def __init__(self, capacity):
        self.capacity, self.items = capacity, []

    def get(self, key):
        for index, (k, v) in enumerate(self.items):
            if k == key:
                self.items.append(self.items.pop(index))
                return v
        return None

    def put(self, key, value):
        self.items = [(k, v) for k, v in self.items if k != key] + [(key, value)]
        if len(self.items) > self.capacity:
            self.items.pop(0)


def check(capacity, ops):
    cache, model = LRUCache(capacity), Model(capacity)
    for op, key, value in ops:
        if op == "get":
            assert cache.get(key) == model.get(key), (capacity, ops)
        else:
            cache.put(key, value)
            model.put(key, value)


for bad in (0, -1):
    try:
        LRUCache(bad)
    except ValueError:
        continue
    raise AssertionError(f"capacity {bad} accepted")
check(1, [("put", 1, 10), ("put", 2, 20), ("get", 1, None), ("get", 2, None)])
check(2, [("put", 1, 10), ("put", 2, 20), ("get", 1, None), ("put", 3, 30),
          ("get", 2, None), ("get", 1, None), ("get", 3, None)])  # get renews recency
check(2, [("put", 1, 10), ("put", 2, 20), ("put", 1, 11), ("put", 3, 30),
          ("get", 1, None), ("get", 2, None)])  # put on an existing key updates and renews
rng = random.Random(4007)
for _ in range(300):
    capacity = rng.randint(1, 4)
    check(capacity, [("get", rng.randint(0, 5), None) if rng.random() < 0.5
                     else ("put", rng.randint(0, 5), rng.randint(0, 9)) for _ in range(30)])
