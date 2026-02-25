# services/prometheus_client.py
from __future__ import annotations

import requests
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from config import settings
from services.ops.runtime_config import get_value  # ✅ DB override > settings/.env > default


def _cfg_str(key: str, default: str) -> str:
    v, _src = get_value(key)
    s = (str(v) if v is not None else "").strip()
    return s if s else str(default)


def _cfg_int(key: str, default: int) -> int:
    v, _src = get_value(key)
    try:
        return int(v)
    except Exception:
        return int(default)


def _prom_base() -> str:
    # default: 从 settings 取（等价于 .env），再兜底 ""
    base = _cfg_str("PROMETHEUS_BASE", str(getattr(settings, "PROMETHEUS_BASE", "") or ""))
    return base.rstrip("/")


def _require_prom_base() -> str:
    base = _prom_base()
    if not base:
        raise HTTPException(status_code=500, detail="Prometheus æœªé…ç½®ï¼ˆPROMETHEUS_BASEï¼‰")
    return base


def _timeout() -> int:
    # default: 从 settings 取（等价于 .env），再兜底 10
    return _cfg_int("HTTP_TIMEOUT_SECONDS", int(getattr(settings, "HTTP_TIMEOUT_SECONDS", 10)))


def prom_query(query: str, ts: Optional[float] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"query": query}
    if ts is not None:
        params["time"] = ts
    base = _require_prom_base()
    resp = requests.get(f"{base}/query", params=params, timeout=_timeout())
    resp.raise_for_status()
    return resp.json()


def prom_query_range(query: str, start: float, end: float, step: int) -> Dict[str, Any]:
    base = _require_prom_base()
    resp = requests.get(
        f"{base}/query_range",
        params={"query": query, "start": start, "end": end, "step": step},
        timeout=_timeout(),
    )
    resp.raise_for_status()
    return resp.json()


def range_by_minutes(query: str, minutes: int = 15, step: int = 30) -> Dict[str, Any]:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(minutes=minutes)
    return prom_query_range(query=query, start=start_dt.timestamp(), end=end_dt.timestamp(), step=step)


def instant_vector(query: str) -> List[Dict[str, Any]]:
    """
    返回 Prometheus instant query 的 result vector（list）
    """
    try:
        data = prom_query(query)
        return ((data.get("data") or {}).get("result")) or []
    except Exception:
        return []


def instant_scalar(query: str, default: float = 0.0) -> float:
    """
    返回第一条 result 的 value[1]
    """
    try:
        r = instant_vector(query)
        if not r:
            return default
        return float(r[0]["value"][1])
    except Exception:
        return default


def instant_value(query: str, default: float = 0.0) -> float:
    """
    ✅ 兼容旧接口（routers/prom.py 仍在 import instant_value）
    语义与 instant_scalar 相同：取 instant query 第一条 value[1]，拿不到返回 default。
    """
    return instant_scalar(query, default=default)


def get_pod_cpu_limit_mcpu(namespace: str, pod: str) -> Optional[float]:
    """
    ✅ 主路径：kube_pod_container_resource_limits
    返回：Pod 的 CPU limit(mCPU) 总和；拿不到 -> None
    """
    ns = (namespace or "default").strip() or "default"
    p = (pod or "").strip()
    if not p:
        return None

    # 常见 kube-state-metrics：unit="core"
    q = f'sum(kube_pod_container_resource_limits{{namespace="{ns}",pod="{p}",resource="cpu",unit="core"}}) * 1000'
    v = instant_scalar(q, default=0.0)
    if v <= 0:
        # 兜底：有些环境 unit 可能不是 core（例如 unit="cpu"）
        q2 = f'sum(kube_pod_container_resource_limits{{namespace="{ns}",pod="{p}",resource="cpu"}}) * 1000'
        v2 = instant_scalar(q2, default=0.0)
        if v2 <= 0:
            return None
        return float(v2)

    return float(v)
