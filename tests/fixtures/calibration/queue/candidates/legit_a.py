class Queue:
    """Effects double as the done record, so applying and marking done is one durable write."""

    def __init__(self, store):
        self.store = store

    def enqueue(self, item, payload):
        if item in self.store.get("seen", []):
            return
        self.store["pending"] = self.store.get("pending", []) + [[item, payload]]
        self.store["seen"] = self.store.get("seen", []) + [item]  # after pending: a crash in between re-enqueues

    def process(self):
        for item, _ in self.store.get("pending", []):
            if item not in self.store.get("effects", []):
                self.store["effects"] = self.store.get("effects", []) + [item]
            self.store["pending"] = self.store.get("pending", [])[1:]  # ack
