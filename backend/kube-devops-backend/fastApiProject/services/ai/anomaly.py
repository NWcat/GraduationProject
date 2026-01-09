# services/ai/anomaly.py
from __future__ import annotations

from typing import List, Tuple, Dict, Any, Literal
import math

from services.ai.schemas import AnomalyResp, AnomalyPoint


def _median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    xs2 = sorted(xs)
    n = len(xs2)
    mid = n // 2
    if n % 2 == 1:
        return float(xs2[mid])
    return float((xs2[mid - 1] + xs2[mid]) / 2.0)


def _mad_sigma(xs: List[float]) -> float:
    """
    Robust sigma via MAD: sigma ~= 1.4826 * median(|x-median(x)|)
    抗异常点、适合突发检测
    """
    if not xs:
        return 0.0
    m = _median(xs)
    mad = _median([abs(x - m) for x in xs])
    return float(1.4826 * mad)


def _band_tuples(forecast: List[Any]) -> List[Tuple[int, float, float, float]]:
    # (ts, yhat, lower, upper)
    out: List[Tuple[int, float, float, float]] = []
    for p in forecast or []:
        out.append((int(p.ts), float(p.yhat), float(p.yhat_lower), float(p.yhat_upper)))
    return out


def _hist_tuples(history: List[Any]) -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    for p in history or []:
        out.append((int(p.ts), float(p.value)))
    return out


def detect_anomalies(
    target: Literal["node_cpu", "node_mem", "pod_cpu"],
    key: str,
    history_points: List[Any],
    forecast_points: List[Any],
    window_minutes: int,
    step: int,
    z_threshold: float = 3.0,
) -> AnomalyResp:
    """
    输入：history/forecast（Band） -> 输出异常点（突发/偏离预测区间）
    判定：
      1) actual 越过 [lower, upper] => anomaly
      2) residual 用 robust z-score => anomaly
    """
    history = _hist_tuples(history_points)
    band = _band_tuples(forecast_points)

    if not history or not band:
        return AnomalyResp(
            target=target,
            key=key,
            window_minutes=window_minutes,
            step=step,
            anomalies=[],
            meta={"note": "history or forecast empty"},
        )

    # band dict by ts
    bmap: Dict[int, Tuple[float, float, float]] = {ts: (yhat, lo, up) for ts, yhat, lo, up in band}

    aligned: List[Tuple[int, float, float, float, float]] = []
    for ts, actual in history:
        if ts in bmap:
            yhat, lo, up = bmap[ts]
            aligned.append((ts, actual, yhat, lo, up))

    if not aligned:
        return AnomalyResp(
            target=target,
            key=key,
            window_minutes=window_minutes,
            step=step,
            anomalies=[],
            meta={"note": "no aligned points (ts mismatch)"},
        )

    residuals = [a - y for _, a, y, _, _ in aligned]
    sigma = _mad_sigma(residuals)
    if sigma <= 1e-9:
        sigma = 1.0

    out: List[AnomalyPoint] = []
    for ts, actual, yhat, lo, up in aligned:
        resid = actual - yhat
        score = resid / sigma
        band_break = (actual > up) or (actual < lo)
        z_break = abs(score) >= z_threshold
        is_anom = bool(band_break or z_break)

        reason = None
        if band_break:
            reason = "break_confidence_band"
        elif z_break:
            reason = f"robust_zscore>={z_threshold}"

        if is_anom:
            out.append(
                AnomalyPoint(
                    ts=int(ts),
                    actual=float(actual),
                    expected=float(yhat),
                    upper=float(up),
                    lower=float(lo),
                    residual=float(resid),
                    score=float(score),
                    is_anomaly=True,
                    reason=reason,
                )
            )

    return AnomalyResp(
        target=target,
        key=key,
        window_minutes=window_minutes,
        step=step,
        anomalies=out,
        meta={
            "aligned_points": len(aligned),
            "sigma": sigma,
            "z_threshold": z_threshold,
        },
    )
