"""Tiny in-process TTL + LRU cache for answered questions.

Swap for Redis in a later brick by keeping this same get/set/make_key surface.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import OrderedDict
from typing import Any

DEFAULT_MAX_ENTRIES = 256
DEFAULT_TTL_SECONDS = 3600


class TTLCache:
    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES,
                 ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.max_entries = max_entries
        self.ttl = ttl_seconds
        self._data: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if time.monotonic() > expires_at:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + self.ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip().lower()


def make_key(dataset_id: str, question: str) -> str:
    digest = hashlib.sha256(
        f"{dataset_id}\x00{normalize_question(question)}".encode()
    ).hexdigest()
    return digest[:32]


answer_cache = TTLCache()
