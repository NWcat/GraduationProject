# services/prometheus_client.py
from __future__ import annotations

import requests
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from config import settings

PROM_BASE = settings.PROMETHEUS_BASE.rstrip("/")  # e.g. http://192.168.100.10:30900/api/v1
TIMEOUT = getattr(settings, "HTTP_TIMEOUT_SECONDS", 10)


def prom_query(query: str, ts: Optional[float] = None) -> Dict[str, Any]:
    """
    GET {PROM_BASE}/query?query=...&time=...
    """
    params: Dict[str, Any] = {"query": query}
    if ts is not None:
        params["time"] = ts

    resp = requests.get(f"{PROM_BASE}/query", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def prom_query_range(query: str, start: float, end: float, step: int) -> Dict[str, Any]:
    """
    GET {PROM_BASE}/query_range?query=...&start=...&end=...&step=...
    """
    resp = requests.get(
        f"{PROM_BASE}/query_range",
        params={"query": query, "start": start, "end": end, "step": step},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def range_by_minutes(query: str, minutes: int = 15, step: int = 30) -> Dict[str, Any]:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(minutes=minutes)
    return prom_query_range(query=query, start=start_dt.timestamp(), end=end_dt.timestamp(), step=step)


def instant_value(query: str, default: float = 0.0) -> float:
    """
    返回第一条 result 的 value[1]，没有则 default
    """
    try:
        data = prom_query(query)
        result = (data.get("data") or {}).get("result") or []
        if not result:
            return default
        return float(result[0]["value"][1])
    except Exception:
        return default
