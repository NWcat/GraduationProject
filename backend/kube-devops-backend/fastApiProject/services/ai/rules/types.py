from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.ai.schemas import SuggestionItem


RuleResult = Optional[SuggestionItem]


@dataclass
class RuleContext:
    target: str
    key: str
    node: Optional[str] = None
    namespace: Optional[str] = None
    pod: Optional[str] = None
    forecast: Any = None
    threshold: Optional[float] = None
    sustain_minutes: Optional[int] = None
    threshold_ratio: Optional[float] = None
    high_threshold_ratio: Optional[float] = None
    observe_ratio: Optional[float] = None
    trigger_ratio: Optional[float] = None
    critical_ratio: Optional[float] = None
    scale_policy: Optional[str] = None
    safe_low: Optional[float] = None
    safe_high: Optional[float] = None


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _to_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return int(default)
        return int(v)
    except Exception:
        return int(default)


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _max_yhat(points: List[Any]) -> float:
    mx = 0.0
    for p in points or []:
        if isinstance(p, dict):
            mx = max(mx, _to_float(p.get("yhat"), 0.0))
        else:
            mx = max(mx, _to_float(_get_attr(p, "yhat", 0.0), 0.0))
    return mx


def _min_yhat_lower(points: List[Any]) -> float:
    mn = None
    for p in points or []:
        v = (
            _to_float(p.get("yhat_lower"), 0.0)
            if isinstance(p, dict)
            else _to_float(_get_attr(p, "yhat_lower", 0.0), 0.0)
        )
        mn = v if mn is None else min(mn, v)
    return float(mn or 0.0)


def _sustain_over_threshold_minutes(
    points: List[Any],
    threshold_value: float,
    step_seconds: int,
) -> int:
    """
    连续超过阈值的持续分钟数（末尾连续段）
    """
    if not points or threshold_value <= 0:
        return 0
    step_seconds = max(int(step_seconds), 1)

    sustain_s = 0
    for p in points:
        y = (
            _to_float(p.get("yhat"), 0.0)
            if isinstance(p, dict)
            else _to_float(_get_attr(p, "yhat", 0.0), 0.0)
        )
        if y >= threshold_value:
            sustain_s += step_seconds
        else:
            sustain_s = 0
    return sustain_s // 60


def _extract_pod_cpu_usages_mcpu(meta: Dict[str, Any]) -> List[float]:
    """
    尝试从 meta 中解析 deployment 维度的 pod cpu 使用列表（mCPU）
    兼容字段：
    - deployment_pod_usages_mcpu: [12.3, 45.6, ...]
    - deployment_pod_cpu_mcpu / deployment_pod_cpu: [{"pod":"a","mcpu":50}, ...]
    - peer_pods_cpu_mcpu / peer_pods_cpu: [...]
    """
    raw = (
        meta.get("deployment_pod_usages_mcpu")
        or meta.get("deployment_pod_cpu_mcpu")
        or meta.get("deployment_pod_cpu")
        or meta.get("peer_pods_cpu_mcpu")
        or meta.get("peer_pods_cpu")
        or None
    )
    if not raw:
        return []

    out: List[float] = []

    if isinstance(raw, list):
        for it in raw:
            if isinstance(it, (int, float)):
                out.append(float(it))
                continue
            if isinstance(it, dict):
                v = (
                    it.get("mcpu")
                    if it.get("mcpu") is not None
                    else it.get("cpu_mcpu")
                    if it.get("cpu_mcpu") is not None
                    else it.get("cpu_m")
                    if it.get("cpu_m") is not None
                    else it.get("cpu")
                )
                if isinstance(v, str):
                    s = v.strip().lower()
                    if s.endswith("m"):
                        out.append(_to_float(s[:-1], 0.0))
                    else:
                        out.append(_to_float(s, 0.0))
                else:
                    out.append(_to_float(v, 0.0))
                continue
            out.append(_to_float(it, 0.0))

    return [x for x in out if x >= 0.0]


def _calc_topk_share(usages: List[float], k: int = 1) -> float:
    if not usages:
        return 0.0
    s = float(sum(usages))
    if s <= 0:
        return 0.0
    k = max(1, int(k))
    topk = sum(sorted(usages, reverse=True)[:k])
    return float(topk) / s


def _stair_replicas_delta(peak_ratio: float, high_threshold_ratio: float) -> int:
    if peak_ratio < high_threshold_ratio:
        return 0
    if peak_ratio < 1.0:
        return 1
    if peak_ratio < 1.2:
        return 2
    if peak_ratio < 1.5:
        return 3
    return 4
