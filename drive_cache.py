"""Bounded, process-local cache for short-lived public Drive listings."""
from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import monotonic


class DriveCache:
    def __init__(self, ttl=45, max_entries=256, max_bytes=8*1024*1024):
        self.ttl, self.max_entries, self.max_bytes = ttl, max_entries, max_bytes
        self.entries = OrderedDict()
        self.lock = Lock()
        self.key_locks = [Lock() for _ in range(32)]
        self.bytes = 0

    def get(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            expiry, value, size = entry
            if expiry <= monotonic():
                self.entries.pop(key)
                self.bytes -= size
                return None
            self.entries.move_to_end(key)
            return deepcopy(value)

    def fetch(self, key, loader, fresh=False):
        if not fresh:
            value = self.get(key)
            if value is not None:
                return value
        with self.key_locks[hash(key) % len(self.key_locks)]:
            if not fresh:
                value = self.get(key)
                if value is not None:
                    return value
            value = loader()  # Errors are never cached.
            import json
            size = len(json.dumps(value, ensure_ascii=False).encode())
            with self.lock:
                previous = self.entries.pop(key, None)
                if previous:
                    self.bytes -= previous[2]
                if size <= self.max_bytes:
                    self.entries[key] = (monotonic()+self.ttl, deepcopy(value), size)
                    self.bytes += size
                    while len(self.entries) > self.max_entries or self.bytes > self.max_bytes:
                        _, removed = self.entries.popitem(last=False)
                        self.bytes -= removed[2]
            return deepcopy(value)
