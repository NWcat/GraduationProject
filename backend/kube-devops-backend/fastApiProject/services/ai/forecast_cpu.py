# services/ai/forecast_cpu.py
from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd

from config import settings
from services.ops.runtime_config import get_value  # ✅ DB override > settings/.env > default

from services.ai.cache import ai_cache
from services.ai.schemas import TsPoint, BandPoint, CpuHistoryResp, CpuForecastResp, ErrorMetrics
from services.ai.metrics import mae, rmse, mape


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
    # default：15（保持你原行为）；若 settings/.env 配了 HTTP_TIMEOUT_SECONDS 会覆盖；
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


def _query_instant(promql: str) -> List[Dict[str, Any]]:
    """
    Prometheus instant query: {base}/query
    返回 data.result 列表
    """
    url = f"{_prom_base()}/query"
    r = requests.get(url, params={"query": promql}, timeout=_http_timeout())
    r.raise_for_status()
    data = r.json()
    return (((data or {}).get("data") or {}).get("result") or [])


def _query_range(promql: str, start: datetime, end: datetime, step_sec: int) -> List[Tuple[int, float]]:
    """
    Prometheus range query: {base}/query_range
    返回 (ts,value) 列表
    """
    url = f"{_prom_base()}/query_range"
    params = {
        "query": promql,
        "start": start.timestamp(),
        "end": end.timestamp(),
        "step": step_sec,
    }
    r = requests.get(url, params=params, timeout=_http_timeout())
    r.raise_for_status()
    data = r.json()
    result = (((data or {}).get("data") or {}).get("result") or [])
    if not result:
        return []

    values = result[0].get("values") or []
    out: List[Tuple[int, float]] = []
    for ts, v in values:
        try:
            out.append((int(float(ts)), float(v)))
        except Exception:
            continue
    return out


def _pick_instance_for_node(node: str) -> Optional[str]:
    """
    把用户传入的 node（k3s/k8s Node 名）解析为 Prometheus 的 instance (ip:9100)。
    ✅ 你 Prometheus 上有：node_uname_info{nodename="k3s-master"} -> instance="192.168.100.10:9100"
    所以优先用 node_uname_info 的 nodename 做精确映射。

    解析规则：
    0) 如果用户直接传 ip:port（包含 :），直接当 instance
    1) node_uname_info{nodename="..."} 精确映射（推荐/最稳）
    2) 兜底：instance=~"{node}.*"（只有你的 instance 本身带主机名时才有用）

    ❌ 不再“随便拿一个 instance”，避免查错节点。
    """
    if ":" in node:
        return node

    # ✅ 1) 最稳：nodename 精确映射
    try:
        rs = _query_instant(f'count by (instance) (node_uname_info{{nodename="{node}"}})')
        if rs:
            return rs[0].get("metric", {}).get("instance")
    except Exception:
        pass

    # 2) 兜底：如果你的 instance 恰好包含 node 名（少数情况）
    try:
        rs = _query_instant(f'count by (instance) (node_cpu_seconds_total{{instance=~"{node}.*"}})')
        if rs:
            return rs[0].get("metric", {}).get("instance")
    except Exception:
        pass

    return None


def _default_node_cpu_promql(node: str) -> Tuple[str, str]:
    """
    节点 CPU 使用率（%） = (1 - idle_rate) * 100
    强制解析 instance，否则报错，避免“查错节点但你不知情”。

    返回 (promql, resolved_instance)
    """
    inst = _pick_instance_for_node(node)
    if not inst:
        raise RuntimeError(
            f'cannot resolve node "{node}" to Prometheus instance. '
            f'Please check node_uname_info{{nodename="{node}"}} exists in Prometheus.'
        )

    promql = (
        f'(1 - avg by (instance) (rate(node_cpu_seconds_total{{mode="idle", instance="{inst}"}}[5m]))) * 100'
    )
    return promql, inst


def _clip_cpu_forecast(points: List[BandPoint]) -> List[BandPoint]:
    """CPU 使用率语义约束：0%~100%"""
    out: List[BandPoint] = []
    for p in points:
        out.append(
            BandPoint(
                ts=p.ts,
                yhat=max(0.0, min(100.0, p.yhat)),
                yhat_lower=max(0.0, min(100.0, p.yhat_lower)),
                yhat_upper=max(0.0, min(100.0, p.yhat_upper)),
            )
        )
    return out


def get_cpu_history(node: str, minutes: int, step: int, promql: Optional[str] = None) -> CpuHistoryResp:
    if promql:
        q = promql
    else:
        q, _inst = _default_node_cpu_promql(node)

    end = _now_utc()
    start = end - timedelta(minutes=minutes)
    points = _query_range(q, start=start, end=end, step_sec=step)
    series = [TsPoint(ts=t, value=v) for (t, v) in points]
    return CpuHistoryResp(node=node, minutes=minutes, step=step, series=series)


def _fit_predict_prophet(
    history: List[Tuple[int, float]],
    horizon_minutes: int,
    step: int
) -> Tuple[List[BandPoint], ErrorMetrics]:
    if len(history) < 20:
        return [], ErrorMetrics(note="not enough data")

    df = pd.DataFrame(history, columns=["ts", "y"])
    df["ds"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_localize(None)
    df = df[["ds", "y"]]
    df["y"] = df["y"].astype(float)

    try:
        from prophet import Prophet  # type: ignore
    except Exception as e:
        raise RuntimeError(f"prophet not installed: {e}")

    model = Prophet(daily_seasonality=False, weekly_seasonality=False)
    model.fit(df)

    periods = max(1, int(horizon_minutes * 60 / step))
    future = model.make_future_dataframe(periods=periods, freq=f"{step}S", include_history=False)
    fc = model.predict(future)

    forecast: List[BandPoint] = []
    for _, row in fc.iterrows():
        ts = int(pd.Timestamp(row["ds"]).timestamp())
        forecast.append(
            BandPoint(
                ts=ts,
                yhat=float(row["yhat"]),
                yhat_lower=float(row["yhat_lower"]),
                yhat_upper=float(row["yhat_upper"]),
            )
        )

    y_true = [v for _, v in history[-periods:]] if len(history) >= periods else []
    y_pred = [p.yhat for p in forecast[: len(y_true)]]
    metrics = ErrorMetrics(
        mae=float(mae(y_true, y_pred)),
        rmse=float(rmse(y_true, y_pred)),
        mape=float(mape(y_true, y_pred)),
        note="tail backtest",
    )
    return forecast, metrics


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

    cache_key = f"cpu_forecast|node={node}|inst={resolved_instance}|m={minutes}|h={horizon}|s={step}|q={hash(q)}"
    cached = ai_cache.get(cache_key)
    if cached:
        return cached

    end = _now_utc()
    start = end - timedelta(minutes=minutes)
    history = _query_range(q, start=start, end=end, step_sec=step)
    history_series = [TsPoint(ts=t, value=v) for (t, v) in history]

    forecast_series, metrics = _fit_predict_prophet(history, horizon_minutes=horizon, step=step)
    forecast_series = _clip_cpu_forecast(forecast_series)

    resp = CpuForecastResp(
        node=node,
        history_minutes=minutes,
        horizon_minutes=horizon,
        step=step,
        history=history_series,
        forecast=forecast_series,
        metrics=metrics,
        meta={
            "promql": q,
            "prom_base": _prom_base(),
            "resolved_instance": resolved_instance,
            "history_points": len(history_series),
            "forecast_points": len(forecast_series),
        },
    )
    ai_cache.set(cache_key, resp, ttl=cache_ttl)
    return resp
