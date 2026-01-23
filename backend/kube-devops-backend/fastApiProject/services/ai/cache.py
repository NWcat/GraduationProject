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


def build_suggestion_snapshot_key(suggestion_id: str) -> str:
    return f"suggestion_snapshot|id={suggestion_id}"


def build_task_key(task_id: str) -> str:
    return f"ai_task|id={task_id}"


def get_task_state(task_id: str) -> Optional[Dict[str, Any]]:
    if not task_id:
        return None
    key = build_task_key(task_id)
    cached = ai_cache.get(key)
    if isinstance(cached, dict):
        return cached
    return None


def set_task_state(task_id: str, state: Dict[str, Any], ttl: int):
    if not task_id:
        return
    key = build_task_key(task_id)
    ai_cache.set(key, state, ttl)
