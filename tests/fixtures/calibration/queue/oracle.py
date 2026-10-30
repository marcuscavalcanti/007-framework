"""Calibration oracle: exactly-once effects when the process crashes at any durable write."""
import copy

from candidate import Queue


class Crash(Exception):
    pass


class Store:
    """Only `store[key] = value` is durable; reads return copies, so in-place mutation never persists."""

    def __init__(self):
        self.data, self.writes, self.crash_at = {}, 0, None

    def __setitem__(self, key, value):
        self.writes += 1
        if self.writes == self.crash_at:
            raise Crash(key)  # the crashing write is not applied
        self.data[key] = copy.deepcopy(value)

    def __getitem__(self, key):
        return copy.deepcopy(self.data[key])

    def __contains__(self, key):
        return key in self.data

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))


IDS = ["a", "b", "c"]


def first_run(store):
    queue = Queue(store)
    for item in IDS:
        queue.enqueue(item, item.upper())
    queue.enqueue("a", "duplicate")  # idempotent by id
    queue.process()


clean = Store()
first_run(clean)
assert clean.get("effects", []) == IDS, clean.data  # each once, in order
Queue(clean).process()
assert clean.get("effects", []) == IDS, clean.data
writes = clean.writes
assert writes > 0
for crash_at in range(1, writes + 1):
    store = Store()
    store.crash_at = crash_at
    try:
        first_run(store)
    except Crash:
        pass
    store.crash_at = None
    queue = Queue(store)  # restart; the producer retries its enqueues (at-least-once delivery)
    for item in IDS:
        queue.enqueue(item, item.upper())
    queue.process()
    effects = store.get("effects", [])
    assert effects == IDS, (crash_at, store.data)  # no loss, no duplicate, FIFO order (spec 8: "em ordem"; review R6)
    Queue(store).process()
    assert store.get("effects", []) == effects, (crash_at, store.data)
