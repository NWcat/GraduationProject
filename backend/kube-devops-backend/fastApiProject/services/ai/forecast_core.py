# services/ai/forecast_core.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional, Tuple

import hashlib
import json
import time

import pandas as pd

from services.ai.metrics import mae, rmse, mape
from services.ai.schemas import BandPoint, ErrorMetrics
from services.prometheus_client import instant_vector, prom_query_range


@dataclass(frozen=True)
class ForecastConfig:
    min_points_absolute: int = 90
    min_points_ratio: float = 0.5
    baseline_band: float = 2.0
    warmup_seconds: int = 0
    prophet_growth: str = "flat"
    prophet_changepoint_prior_scale: float = 0.01


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def stable_hash(s: str) -> str:
    if s is None:
        s = ""
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16]


def _stringify_value(v: Any) -> str:
    if isinstance(v, (dict, list, tuple)):
        try:
            return json.dumps(v, sort_keys=True, ensure_ascii=True, default=str)
        except Exception:
            return str(v)
    return str(v)


def build_cache_key(prefix: str, **kwargs: Any) -> str:
    parts: List[str] = [prefix]
    for k in sorted(kwargs.keys()):
        v_str = _stringify_value(kwargs[k])
        if len(v_str) > 50:
            v_str = stable_hash(v_str)
        parts.append(f"{k}={v_str}")
    return "|".join(parts)


def query_range_tuples(promql: str, start_ts: int, end_ts: int, step: int) -> List[Tuple[int, float]]:
    data = prom_query_range(query=promql, start=float(start_ts), end=float(end_ts), step=step)
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


def clip_range(points: Iterable[BandPoint], lo: Optional[float], hi: Optional[float]) -> List[BandPoint]:
    out: List[BandPoint] = []
    for p in points:
        yhat = p.yhat
        yhat_lower = p.yhat_lower
        yhat_upper = p.yhat_upper
        if lo is not None:
            yhat = max(lo, yhat)
            yhat_lower = max(lo, yhat_lower)
            yhat_upper = max(lo, yhat_upper)
        if hi is not None:
            yhat = min(hi, yhat)
            yhat_lower = min(hi, yhat_lower)
            yhat_upper = min(hi, yhat_upper)
        out.append(BandPoint(ts=p.ts, yhat=yhat, yhat_lower=yhat_lower, yhat_upper=yhat_upper))
    return out


def clip_non_negative(points: Iterable[BandPoint]) -> List[BandPoint]:
    out: List[BandPoint] = []
    for p in points:
        out.append(
            BandPoint(
                ts=p.ts,
                yhat=max(0.0, p.yhat),
                yhat_lower=max(0.0, p.yhat_lower),
                yhat_upper=max(0.0, p.yhat_upper),
            )
        )
    return out


def pick_instance_for_node(node: str) -> Optional[str]:
    if ":" in node:
        return node

    try:
        rs = instant_vector(f'count by (instance) (node_uname_info{{nodename="{node}"}})')
        if rs:
            return (rs[0].get("metric") or {}).get("instance")
    except Exception:
        pass

    try:
        rs = instant_vector(f'count by (instance) (node_uname_info{{instance=~"{node}.*"}})')
        if rs:
            return (rs[0].get("metric") or {}).get("instance")
    except Exception:
        pass

    return None


def require_instance_for_node(node: str) -> str:
    inst = pick_instance_for_node(node)
    if not inst:
        raise RuntimeError(
            f'cannot resolve node "{node}" to Prometheus instance. '
            f'Please check node_uname_info{{nodename="{node}"}} exists in Prometheus.'
        )
    return inst


def _baseline_forecast(
    history: List[Tuple[int, float]],
    periods: int,
    step: int,
    config: ForecastConfig,
    note: str,
) -> Tuple[List[BandPoint], ErrorMetrics]:
    band = max(0.0, float(config.baseline_band))
    if not history:
        start_ts = int(time.time())
        forecast = [
            BandPoint(
                ts=start_ts + (i + 1) * step,
                yhat=0.0,
                yhat_lower=0.0,
                yhat_upper=band,
            )
            for i in range(periods)
        ]
        return forecast, ErrorMetrics(note=note)

    last_ts, last_val = history[-1]
    last_val = max(0.0, float(last_val))
    forecast = [
        BandPoint(
            ts=last_ts + (i + 1) * step,
            yhat=last_val,
            yhat_lower=max(0.0, last_val - band),
            yhat_upper=max(0.0, last_val + band),
        )
        for i in range(periods)
    ]
    return forecast, ErrorMetrics(note=note)


def fit_predict_prophet(
    history: List[Tuple[int, float]],
    horizon_minutes: int,
    step: int,
    config: Optional[ForecastConfig] = None,
) -> Tuple[List[BandPoint], ErrorMetrics]:
    cfg = config or ForecastConfig()
    periods = max(1, int(horizon_minutes * 60 / step))
    ratio_points = int(periods * float(cfg.min_points_ratio))
    dynamic_min = max(30, int(cfg.min_points_absolute), ratio_points)

    clean = history
    if cfg.warmup_seconds > 0 and history:
        t0 = history[0][0]
        clean = [(t, v) for (t, v) in history if t >= t0 + int(cfg.warmup_seconds)]
        if not clean:
            clean = history

    points_len = len(clean)
    holdout_n = int(points_len * 0.2) if points_len > 0 else 0
    train_len = points_len - holdout_n
    valid_len = holdout_n

    if not history:
        note = f"baseline|points={points_len}|min_required={dynamic_min}|train={train_len}|valid={valid_len}"
        return _baseline_forecast(clean, periods, step, cfg, note)

    if points_len < dynamic_min:
        note = f"baseline|points={points_len}|min_required={dynamic_min}|train={train_len}|valid={valid_len}"
        return _baseline_forecast(clean, periods, step, cfg, note)

    df = pd.DataFrame(clean, columns=["ts", "y"])
    df["ds"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_localize(None)
    df = df[["ds", "y"]]
    df["y"] = df["y"].astype(float)

    try:
        from prophet import Prophet  # type: ignore
    except Exception as exc:
        note = f"baseline|points={points_len}|min_required={dynamic_min}|train={train_len}|valid={valid_len}"
        return _baseline_forecast(clean, periods, step, cfg, note + f"|prophet_error={exc}")

    model = Prophet(
        growth=cfg.prophet_growth,
        daily_seasonality=False,
        weekly_seasonality=False,
        yearly_seasonality=False,
        changepoint_prior_scale=float(cfg.prophet_changepoint_prior_scale),
    )
    model.fit(df)

    future = model.make_future_dataframe(periods=periods, freq=f"{step}S", include_history=False)
    forecast_df = model.predict(future)

    forecast: List[BandPoint] = []
    for _, row in forecast_df.iterrows():
        ts = int(pd.Timestamp(row["ds"]).timestamp())
        forecast.append(
            BandPoint(
                ts=ts,
                yhat=max(0.0, float(row["yhat"])),
                yhat_lower=max(0.0, float(row["yhat_lower"])),
                yhat_upper=max(0.0, float(row["yhat_upper"])),
            )
        )

    if not forecast:
        note = f"baseline|points={points_len}|min_required={dynamic_min}|train={train_len}|valid={valid_len}"
        return _baseline_forecast(clean, periods, step, cfg, note + "|prophet_empty")

    if holdout_n <= 0 or train_len < 2:
        metrics = ErrorMetrics(
            note=f"prophet|points={points_len}|min_required={dynamic_min}|train={train_len}|valid={valid_len}"
        )
        return forecast, metrics

    train = clean[:-holdout_n]
    valid = clean[-holdout_n:]

    train_df = pd.DataFrame(train, columns=["ts", "y"])
    train_df["ds"] = pd.to_datetime(train_df["ts"], unit="s", utc=True).dt.tz_localize(None)
    train_df = train_df[["ds", "y"]]
    train_df["y"] = train_df["y"].astype(float)

    model_bt = Prophet(
        growth=cfg.prophet_growth,
        daily_seasonality=False,
        weekly_seasonality=False,
        yearly_seasonality=False,
        changepoint_prior_scale=float(cfg.prophet_changepoint_prior_scale),
    )
    model_bt.fit(train_df)

    future_valid = pd.DataFrame(
        {"ds": [pd.to_datetime(ts, unit="s", utc=True).tz_localize(None) for ts, _ in valid]}
    )
    valid_pred = model_bt.predict(future_valid)
    y_true = [v for _, v in valid]
    y_pred = [max(0.0, float(v)) for v in valid_pred["yhat"].tolist()]

    metrics = ErrorMetrics(
        mae=float(mae(y_true, y_pred)),
        rmse=float(rmse(y_true, y_pred)),
        mape=float(mape(y_true, y_pred)),
        note=f"prophet|points={points_len}|min_required={dynamic_min}|train={train_len}|valid={valid_len}",
    )
    return forecast, metrics
