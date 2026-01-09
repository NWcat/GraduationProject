# services/ai/cache.py
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class CacheItem:
    expire_at: float
    value: Any


class TTLCache:
    def __init__(self):
        self._data: Dict[str, CacheItem] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._data.get(key)
        if not item:
            return None
        if time.time() > item.expire_at:
            self._data.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: Any, ttl: int):
        self._data[key] = CacheItem(expire_at=time.time() + ttl, value=value)

    def clear(self):
        self._data.clear()


ai_cache = TTLCache()
