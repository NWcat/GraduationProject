# services/ai/forecast_pod_cpu.py
from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any

from services.ai.cache import ai_cache
from services.ai.schemas import TsPoint, BandPoint, PodCpuHistoryResp, PodCpuForecastResp, ErrorMetrics
from services.ai.forecast_core import (
    ForecastConfig,
    clip_non_negative,
    stable_hash,
    build_contract_meta,
    build_history_series,
    build_forecast_series,
)
from services.ops.runtime_config import get_value  # ✅DB override > settings/.env > default
from services.monitoring.prometheus_client import instant_vector

def _baseline_points(history: list[tuple[int, float]], forecast: list[BandPoint]) -> list[TsPoint]:
    if not forecast:
        return []
    last_val = history[-1][1] if history else 0.0
    val = max(0.0, float(last_val))
    return [TsPoint(ts=p.ts, value=val) for p in forecast]


POD_CPU_CONFIG = ForecastConfig(
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
    # 默认保持原行为：15s；如果 settings/.env 配了 HTTP_TIMEOUT_SECONDS 或 DB override（若你将来加进SPECS）则覆盖
    try:
        from config import settings  # type: ignore
        default = int(getattr(settings, "HTTP_TIMEOUT_SECONDS", 15) or 15)
    except Exception:
        default = 15
    return _cfg_int("HTTP_TIMEOUT_SECONDS", default)


def _prom_base() -> str:
    # ✅优先 DB override，其次 settings/.env，最后 default
    base = ""
    try:
        from config import settings  # type: ignore
        base = _cfg_str("PROMETHEUS_BASE", str(getattr(settings, "PROMETHEUS_BASE", "") or ""))
    except Exception:
        base = _cfg_str("PROMETHEUS_BASE", "")

    if not base:
        base = "http://localhost:9090/api/v1"
    return str(base).rstrip("/")


def _query_instant(promql: str) -> List[Dict[str, Any]]:
    return instant_vector(promql) or []


def _default_pod_cpu_promql(namespace: str, pod: str, window: str = "2m") -> str:
    """
    Pod CPU 使用量（mCPU）：
      sum(rate(container_cpu_usage_seconds_total{namespace="x",pod="y",container!="",image!=""}[2m])) * 1000

    ⚠️ 依赖你 Prometheus 抓到 kubelet/cadvisor 指标
    """
    return (
        f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",pod="{pod}",container!="",image!=""}}[{window}])) * 1000'
    )


def _try_get_pod_cpu_limit_mcpu(namespace: str, pod: str) -> Optional[float]:
    """
    如果你装了 kube-state-metrics，就能取到 limit：
      kube_pod_container_resource_limits{resource="cpu", unit="core", namespace="x", pod="y"}
    这里返回 Pod 汇总 limit(mCPU)。拿不到就返回 None。
    """
    promql = (
        f'sum(kube_pod_container_resource_limits{{resource="cpu", unit="core", namespace="{namespace}", pod="{pod}"}}) * 1000'
    )
    try:
        rs = _query_instant(promql)
        if not rs:
            return None
        v = rs[0].get("value", [None, None])[1]
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def get_pod_cpu_history(
    namespace: str,
    pod: str,
    minutes: int,
    step: int,
    promql: Optional[str] = None,
) -> PodCpuHistoryResp:
    q = promql or _default_pod_cpu_promql(namespace, pod)
    points = build_history_series(q, minutes, step)
    series = [TsPoint(ts=t, value=v) for (t, v) in points]

    limit_mcpu = _try_get_pod_cpu_limit_mcpu(namespace, pod)
    meta: Dict[str, Any] = build_contract_meta(
        target="pod_cpu",
        unit="mCPU",
        promql=q,
        history_points=len(series),
        forecast_points=0,
    )
    meta.update(
        {
            "prom_base": _prom_base(),
            "points": len(series),
            "limit_mcpu": limit_mcpu,
        }
    )
    return PodCpuHistoryResp(namespace=namespace, pod=pod, minutes=minutes, step=step, series=series, meta=meta)


def get_pod_cpu_forecast(
    namespace: str,
    pod: str,
    minutes: int,
    horizon: int,
    step: int,
    cache_ttl: int = 300,
    promql: Optional[str] = None,
) -> PodCpuForecastResp:
    q = promql or _default_pod_cpu_promql(namespace, pod)
    cache_key = f"pod_cpu_forecast|ns={namespace}|pod={pod}|m={minutes}|h={horizon}|s={step}|q={stable_hash(q)}"
    cached = ai_cache.get(cache_key)
    if cached:
        return cached

    history, forecast_series, metrics = build_forecast_series(
        q,
        minutes,
        horizon,
        step,
        POD_CPU_CONFIG,
        clip_fn=clip_non_negative,
    )
    history_series = [TsPoint(ts=t, value=v) for (t, v) in history]

    limit_mcpu = _try_get_pod_cpu_limit_mcpu(namespace, pod)

    resp = PodCpuForecastResp(
        namespace=namespace,
        pod=pod,
        history_minutes=minutes,
        horizon_minutes=horizon,
        step=step,
        history=history_series,
        forecast=forecast_series,
        metrics=metrics,
        meta={
            **build_contract_meta(
                target="pod_cpu",
                unit="mCPU",
                promql=q,
                history_points=len(history_series),
                forecast_points=len(forecast_series),
            ),
            "prom_base": _prom_base(),
            "limit_mcpu": limit_mcpu,
            "baseline_points": _baseline_points(history, forecast_series),
        },
    )
    ai_cache.set(cache_key, resp, ttl=cache_ttl)
    return resp
