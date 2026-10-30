class Queue:
    """M1: acknowledges before the effect is durable, so a crash in between loses the item."""

    def __init__(self, store):
        self.store = store

    def enqueue(self, item, payload):
        if item in self.store.get("seen", []):
            return
        self.store["pending"] = self.store.get("pending", []) + [[item, payload]]
        self.store["seen"] = self.store.get("seen", []) + [item]

    def process(self):
        for item, _ in self.store.get("pending", []):
            self.store["pending"] = self.store.get("pending", [])[1:]  # ack first
            if item not in self.store.get("effects", []):
                self.store["effects"] = self.store.get("effects", []) + [item]
