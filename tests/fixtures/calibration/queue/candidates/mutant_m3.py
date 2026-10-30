class Queue:
    """M3 (review r25-r32 R6): after a crash, remaining items run in reverse order; exactly-once is kept, FIFO order is not."""

    def __init__(self, store):
        self.store = store

    def enqueue(self, item, payload):
        if item in self.store.get("seen", []):
            return
        self.store["pending"] = self.store.get("pending", []) + [[item, payload]]
        self.store["seen"] = self.store.get("seen", []) + [item]

    def process(self):
        pending = self.store.get("pending", [])
        if self.store.get("effects", []):
            pending = pending[::-1]
        for item, _ in pending:
            if item not in self.store.get("effects", []):
                self.store["effects"] = self.store.get("effects", []) + [item]
            self.store["pending"] = [entry for entry in self.store.get("pending", []) if entry[0] != item]  # ack this item
