import time
from collections import deque


class ShortTermMemory:
    def __init__(self, max_items=50, ttl=60):
        self.events = deque(maxlen=max_items)

    def add(self, type, data):
        self.events.append({
            "type": type,
            "data": data,
            "timestamp": time.time()
        })

    def get_recent(self, seconds=30):
        cutoff = time.time() - seconds
        return [e for e in self.events if e["timestamp"] > cutoff]
