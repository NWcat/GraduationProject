# services/ai/forecast_cpu.py
from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any

from config import settings
from services.ops.runtime_config import get_value  # ✅DB override > settings/.env > default

from services.ai.cache import ai_cache
from services.ai.schemas import TsPoint, BandPoint, CpuHistoryResp, CpuForecastResp, ErrorMetrics
from services.ai.forecast_core import (
    ForecastConfig,
    clip_range,
    stable_hash,
    build_contract_meta,
    build_history_series,
    build_forecast_series,
    require_instance_for_node,
)


def _baseline_points(history: list[tuple[int, float]], forecast: list[BandPoint]) -> list[TsPoint]:
    if not forecast:
        return []
    last_val = history[-1][1] if history else 0.0
    val = max(0.0, float(last_val))
    if val > 100.0:
        val = 100.0
    return [TsPoint(ts=p.ts, value=val) for p in forecast]


CPU_CONFIG = ForecastConfig(
    min_points_absolute=90,
    min_points_ratio=0.5,
    baseline_band=2.0,
    warmup_seconds=6 * 60,
    prophet_growth="flat",
    prophet_changepoint_prior_scale=0.01,
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
    # default？5（保持你原行为）；若 settings/.env 配了 HTTP_TIMEOUT_SECONDS 会覆盖；
    # 将来加进 SPECS 后也可被 DB override 覆盖
    default = int(getattr(settings, "HTTP_TIMEOUT_SECONDS", 15) or 15)
    return _cfg_int("HTTP_TIMEOUT_SECONDS", default)


def _prom_base() -> str:
    """
    生效优先级：DB override（前端） > settings/.env > default
    """
    base = _cfg_str("PROMETHEUS_BASE", str(getattr(settings, "PROMETHEUS_BASE", "") or ""))
    if not base:
        base = "http://localhost:9090/api/v1"
    return base.rstrip("/")


def _default_node_cpu_promql(node: str) -> Tuple[str, str]:
    """
    节点 CPU 使用率（%）= (1 - idle_rate) * 100
    强制解析 instance，否则报错，避免“查错节点但你不知情”。

    返回 (promql, resolved_instance)
    """
    inst = require_instance_for_node(node)

    promql = (
        f'(1 - avg by (instance) (rate(node_cpu_seconds_total{{mode="idle", instance="{inst}"}}[5m]))) * 100'
    )
    return promql, inst


def get_cpu_history(node: str, minutes: int, step: int, promql: Optional[str] = None) -> CpuHistoryResp:
    if promql:
        q = promql
        resolved_instance: Optional[str] = None
    else:
        q, resolved_instance = _default_node_cpu_promql(node)

    points = build_history_series(q, minutes, step)
    series = [TsPoint(ts=t, value=v) for (t, v) in points]
    base_meta = build_contract_meta(
        target="node_cpu",
        unit="%",
        promql=q,
        history_points=len(series),
        forecast_points=0,
    )
    base_meta.update(
        {
            "prom_base": _prom_base(),
            "resolved_instance": resolved_instance,
        }
    )
    return CpuHistoryResp(node=node, minutes=minutes, step=step, series=series, meta=base_meta)


def get_cpu_forecast(
    node: str,
    minutes: int,
    horizon: int,
    step: int,
    cache_ttl: int = 300,
    promql: Optional[str] = None,
) -> CpuForecastResp:
    resolved_instance: Optional[str] = None

    if promql:
        q = promql
    else:
        q, resolved_instance = _default_node_cpu_promql(node)

    cache_key = f"cpu_forecast|node={node}|inst={resolved_instance}|m={minutes}|h={horizon}|s={step}|q={stable_hash(q)}"
    cached = ai_cache.get(cache_key)
    if cached:
        return cached

    history, forecast_series, metrics = build_forecast_series(
        q,
        minutes,
        horizon,
        step,
        CPU_CONFIG,
        clip_fn=lambda pts: clip_range(pts, 0.0, 100.0),
    )
    history_series = [TsPoint(ts=t, value=v) for (t, v) in history]

    resp = CpuForecastResp(
        node=node,
        history_minutes=minutes,
        horizon_minutes=horizon,
        step=step,
        history=history_series,
        forecast=forecast_series,
        metrics=metrics,
        meta={
            **build_contract_meta(
                target="node_cpu",
                unit="%",
                promql=q,
                history_points=len(history_series),
                forecast_points=len(forecast_series),
            ),
            "prom_base": _prom_base(),
            "resolved_instance": resolved_instance,
            "baseline_points": _baseline_points(history, forecast_series),
        },
    )
    ai_cache.set(cache_key, resp, ttl=cache_ttl)
    return resp
