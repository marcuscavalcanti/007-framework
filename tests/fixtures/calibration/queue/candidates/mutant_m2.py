class Queue:
    """M2: effect and done marker are separate writes, effect first, so a crash in between duplicates."""

    def __init__(self, store):
        self.store = store

    def enqueue(self, item, payload):
        if item in self.store.get("seen", []):
            return
        self.store["pending"] = self.store.get("pending", []) + [[item, payload]]
        self.store["seen"] = self.store.get("seen", []) + [item]

    def process(self):
        for item, _ in self.store.get("pending", []):
            if item not in self.store.get("done", []):
                self.store["effects"] = self.store.get("effects", []) + [item]
                self.store["done"] = self.store.get("done", []) + [item]
            self.store["pending"] = self.store.get("pending", [])[1:]
