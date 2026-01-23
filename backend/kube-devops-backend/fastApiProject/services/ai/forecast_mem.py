# services/ai/forecast_mem.py
from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any

from config import settings
from services.ops.runtime_config import get_value  # ✅DB override > settings/.env > default

from services.ai.cache import ai_cache
from services.ai.schemas import TsPoint, BandPoint, MemHistoryResp, MemForecastResp, ErrorMetrics
from services.ai.forecast_core import (
    ForecastConfig,
    clip_range,
    stable_hash,
    build_contract_meta,
    build_history_series,
    build_forecast_series,
    require_instance_for_node,
)


MEM_CONFIG = ForecastConfig(
    min_points_absolute=30,
    min_points_ratio=0.5,
    baseline_band=2.0,
    warmup_seconds=0,
    prophet_growth="linear",
    prophet_changepoint_prior_scale=0.05,
)


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


def _http_timeout() -> int:
    # default？5（保持你原逻辑）；若 settings/.env 配了 HTTP_TIMEOUT_SECONDS 会覆盖；
    # 将来你把 HTTP_TIMEOUT_SECONDS 加进 SPECS 后，也能被 DB override 覆盖
    default = int(getattr(settings, "HTTP_TIMEOUT_SECONDS", 15) or 15)
    return _cfg_int("HTTP_TIMEOUT_SECONDS", default)


def _prom_base() -> str:
    """
    读取 Prometheus Base URL（包含/api/v1）
    规则：DB 覆盖优先 -> 否则回落 settings/.env 默认 -> 否则 default
    """
    base = _cfg_str("PROMETHEUS_BASE", str(getattr(settings, "PROMETHEUS_BASE", "") or ""))
    if not base:
        base = "http://localhost:9090/api/v1"
    return str(base).rstrip("/")


def _default_node_mem_promql(node: str) -> Tuple[str, str]:
    """
    节点内存使用率 = (1 - MemAvailable/MemTotal) * 100
    强制解析 instance，否则报错。
    """
    inst = require_instance_for_node(node)

    q = (
        f'(1 - (avg by (instance) (node_memory_MemAvailable_bytes{{instance="{inst}"}})'
        f' / avg by (instance) (node_memory_MemTotal_bytes{{instance="{inst}"}}))) * 100'
    )
    return q, inst


def _clip_percent(points: List[BandPoint]) -> List[BandPoint]:
    return clip_range(points, 0.0, 100.0)


def get_mem_history(node: str, minutes: int, step: int, promql: Optional[str] = None) -> MemHistoryResp:
    if promql:
        q = promql
        resolved_instance: Optional[str] = None
    else:
        q, resolved_instance = _default_node_mem_promql(node)

    points = build_history_series(q, minutes, step)
    series = [TsPoint(ts=t, value=v) for (t, v) in points]
    base_meta = build_contract_meta(
        target="node_mem",
        unit="%",
        promql=q,
        history_points=len(series),
        forecast_points=0,
    )
    base_meta.update(
        {
            "prom_base": _prom_base(),
            "resolved_instance": resolved_instance,
            "points": len(series),
        }
    )
    return MemHistoryResp(
        node=node,
        minutes=minutes,
        step=step,
        series=series,
        meta=base_meta,
    )


def get_mem_forecast(
    node: str,
    minutes: int,
    horizon: int,
    step: int,
    cache_ttl: int = 300,
    promql: Optional[str] = None,
) -> MemForecastResp:
    resolved_instance: Optional[str] = None

    if promql:
        q = promql
    else:
        q, resolved_instance = _default_node_mem_promql(node)

    cache_key = f"mem_forecast|node={node}|inst={resolved_instance}|m={minutes}|h={horizon}|s={step}|q={stable_hash(q)}"
    cached = ai_cache.get(cache_key)
    if cached:
        return cached

    history, forecast_series, metrics = build_forecast_series(
        q,
        minutes,
        horizon,
        step,
        MEM_CONFIG,
        clip_fn=_clip_percent,
    )
    history_series = [TsPoint(ts=t, value=v) for (t, v) in history]

    resp = MemForecastResp(
        node=node,
        history_minutes=minutes,
        horizon_minutes=horizon,
        step=step,
        history=history_series,
        forecast=forecast_series,
        metrics=metrics,
        meta={
            **build_contract_meta(
                target="node_mem",
                unit="%",
                promql=q,
                history_points=len(history_series),
                forecast_points=len(forecast_series),
            ),
            "prom_base": _prom_base(),
            "resolved_instance": resolved_instance,
        },
    )
    ai_cache.set(cache_key, resp, ttl=cache_ttl)
    return resp
