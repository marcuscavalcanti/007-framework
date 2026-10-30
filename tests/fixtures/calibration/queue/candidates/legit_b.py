class Queue:
    """One record per write: the queue (order + payloads) and the effects list."""

    def __init__(self, store):
        self.store = store

    def _queue(self):
        return self.store.get("queue", {"order": [], "payloads": {}})

    def enqueue(self, item, payload):
        queue = self._queue()
        if item in queue["order"] or item in self.store.get("effects", []):
            return
        queue["order"].append(item)
        queue["payloads"][item] = payload
        self.store["queue"] = queue

    def process(self):
        while self._queue()["order"]:
            queue = self._queue()
            item = queue["order"][0]
            if item not in self.store.get("effects", []):
                self.store["effects"] = self.store.get("effects", []) + [item]
            queue["order"].pop(0)
            del queue["payloads"][item]
            self.store["queue"] = queue
