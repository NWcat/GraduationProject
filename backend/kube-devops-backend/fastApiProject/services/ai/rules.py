# services/ai/rules.py
from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional

from services.ai.schemas import SuggestionsResp, SuggestionItem, ActionHint
from services.ai.scale_policy import calc_linear_target_replicas

ScalePolicy = Literal["stair", "linear"]


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


# ========================= 节点 CPU =========================
def generate_node_cpu_suggestions(
    node: str,
    forecast: Any,  # CpuForecastResp-like
    threshold: float = 85.0,
    sustain_minutes: int = 15,
) -> SuggestionsResp:
    """
    节点 CPU：这里假定 forecast.history/forecast.forecast 的 value 都是 “百分比(0~100)”
    如果你的 forecast_cpu 返回的是 0~1 或 核数，请在 forecast_cpu 里统一换算。
    """
    key = node
    meta = _get_attr(forecast, "meta", None) or {}
    points = _get_attr(forecast, "forecast", []) or []
    step = _to_int(_get_attr(forecast, "step", 60), 60)

    peak = _max_yhat(points)
    sustain_over = _sustain_over_threshold_minutes(points, float(threshold), step)

    suggestions: List[SuggestionItem] = []

    if sustain_over < int(sustain_minutes):
        suggestions.append(
            SuggestionItem(
                severity="info",
                title="节点 CPU 预测未达到持续超阈值条件",
                evidence={
                    "node": node,
                    "peak": round(peak, 2),
                    "threshold": threshold,
                    "sustain_over_minutes": sustain_over,
                    "required_sustain_minutes": sustain_minutes,
                },
                rationale="预测峰值或持续时间不足以触发动作建议。",
                action=ActionHint(kind="no_action", params={}),
            )
        )
        return SuggestionsResp(target="node_cpu", key=key, suggestions=suggestions, meta=meta)

    severity: Literal["info", "warning", "critical"] = "warning"
    if peak >= min(100.0, threshold + 10.0):
        severity = "critical"

    suggestions.append(
        SuggestionItem(
            severity=severity,
            title="节点 CPU 持续高负载，建议排查与扩容",
            evidence={
                "node": node,
                "peak": round(peak, 2),
                "threshold": threshold,
                "sustain_over_minutes": sustain_over,
            },
            rationale="预测显示 CPU 将持续高于阈值，可能导致调度拥塞/延迟上升。",
            action=ActionHint(kind="add_node", params={"node": node}),
        )
    )
    return SuggestionsResp(target="node_cpu", key=key, suggestions=suggestions, meta=meta)


# ========================= 节点 Mem =========================
def generate_node_mem_suggestions(
    node: str,
    forecast: Any,  # MemForecastResp-like
    threshold: float = 85.0,
    sustain_minutes: int = 15,
) -> SuggestionsResp:
    """
    节点 Mem：同上，假定单位是“百分比(0~100)”
    """
    key = node
    meta = _get_attr(forecast, "meta", None) or {}
    points = _get_attr(forecast, "forecast", []) or []
    step = _to_int(_get_attr(forecast, "step", 60), 60)

    peak = _max_yhat(points)
    sustain_over = _sustain_over_threshold_minutes(points, float(threshold), step)

    suggestions: List[SuggestionItem] = []

    if sustain_over < int(sustain_minutes):
        suggestions.append(
            SuggestionItem(
                severity="info",
                title="节点内存预测未达到持续超阈值条件",
                evidence={
                    "node": node,
                    "peak": round(peak, 2),
                    "threshold": threshold,
                    "sustain_over_minutes": sustain_over,
                    "required_sustain_minutes": sustain_minutes,
                },
                rationale="预测峰值或持续时间不足以触发动作建议。",
                action=ActionHint(kind="no_action", params={}),
            )
        )
        return SuggestionsResp(target="node_mem", key=key, suggestions=suggestions, meta=meta)

    severity: Literal["info", "warning", "critical"] = "warning"
    if peak >= min(100.0, threshold + 10.0):
        severity = "critical"

    suggestions.append(
        SuggestionItem(
            severity=severity,
            title="节点内存持续高负载，建议排查与扩容",
            evidence={
                "node": node,
                "peak": round(peak, 2),
                "threshold": threshold,
                "sustain_over_minutes": sustain_over,
            },
            rationale="预测显示内存将持续高位，可能引发 OOM 或频繁回收导致抖动。",
            action=ActionHint(kind="add_node", params={"node": node}),
        )
    )
    return SuggestionsResp(target="node_mem", key=key, suggestions=suggestions, meta=meta)


# ========================= Pod CPU =========================
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


def generate_pod_cpu_suggestions(
    namespace: str,
    pod: str,
    forecast: Any,  # PodCpuForecastResp-like
    threshold_ratio: float = 0.80,
    high_threshold_ratio: float = 0.90,
    sustain_minutes: int = 10,
    scale_policy: ScalePolicy = "stair",
    safe_low: float = 0.6,
    safe_high: float = 0.7,
) -> SuggestionsResp:
    """
    修正版（让你能看到 tune_requests_limits 的建议）：
    1) 加入热点识别：peer pods CPU（meta里） + Top1/TopK 占比过高 -> 优先 tune_requests_limits
    2) 单/少副本且 peak_ratio >= 1.0（疑似 throttle/资源不足）-> 也优先 tune_requests_limits
    3) tune params 字段统一为 cpu_*_m / mem_*_mb（不要用 *_mcpu），以匹配前端回填和后端 execute 覆盖
    4) limit 缺失时：若能定位 Deployment，则给 tune_requests_limits（带 name），否则 fallback investigate_logs
    """
    key = f"{namespace}/{pod}"
    meta = _get_attr(forecast, "meta", None) or {}
    points = _get_attr(forecast, "forecast", []) or []
    step = _to_int(_get_attr(forecast, "step", 60), 60)

    limit_mcpu = _to_float(meta.get("limit_mcpu"), 0.0)
    unit = meta.get("unit") or "mCPU"

    controller_kind = str(meta.get("controller_kind") or "")
    deployment_name = str(meta.get("deployment_name") or "unknown")
    current_replicas = _to_int(meta.get("current_replicas"), 0)

    suggestions: List[SuggestionItem] = []

    # 0) 无 limit：无法做比例判断；尽量给出可执行的 tune（需要 deployment）
    if limit_mcpu <= 0:
        if controller_kind == "ReplicaSet" and deployment_name != "unknown":
            suggestions.append(
                SuggestionItem(
                    severity="warning",
                    title="未检测到 Pod CPU limit，建议先为 Deployment 设置 requests/limits",
                    evidence={
                        "pod": key,
                        "deployment": f"{namespace}/{deployment_name}",
                        "limit_mcpu": None,
                        "unit": unit,
                    },
                    rationale="缺少 resources.limits.cpu（或 requests.cpu）无法做比例判断；先补齐资源配置。",
                    action=ActionHint(
                        kind="tune_requests_limits",
                        params={
                            "scope": "deployment",
                            "namespace": namespace,
                            "name": deployment_name,
                            # 给保守默认值（也允许你弹窗编辑覆盖）
                            "cpu_request_m": 100,
                            "cpu_limit_m": 200,
                            "reason": "missing_limit",
                        },
                    ),
                )
            )
        else:
            suggestions.append(
                SuggestionItem(
                    severity="warning",
                    title="未检测到 Pod CPU limit，且无法定位 Deployment",
                    evidence={
                        "pod": key,
                        "controller_kind": controller_kind,
                        "deployment_name": deployment_name,
                    },
                    rationale="请先确认该 Pod 是否由 Deployment 管理，并补齐 resources 配置。",
                    action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
                )
            )
        return SuggestionsResp(target="pod_cpu", key=key, suggestions=suggestions, meta=meta)

    peak_mcpu = _max_yhat(points)
    peak_ratio = float(peak_mcpu) / max(float(limit_mcpu), 1.0)

    threshold_mcpu = float(limit_mcpu) * float(threshold_ratio)
    sustain_over = _sustain_over_threshold_minutes(points, threshold_mcpu, step)
    need_action = sustain_over >= int(sustain_minutes)

    if not need_action:
        suggestions.append(
            SuggestionItem(
                severity="info",
                title="Pod CPU 预测未达到持续超阈值条件",
                evidence={
                    "pod": key,
                    "limit_mcpu": round(limit_mcpu, 2),
                    "unit": unit,
                    "peak_mcpu": round(peak_mcpu, 2),
                    "peak_ratio": round(peak_ratio, 3),
                    "threshold_ratio": threshold_ratio,
                    "sustain_over_minutes": sustain_over,
                    "required_sustain_minutes": sustain_minutes,
                },
                rationale="预测峰值或持续时间不足以触发动作建议。",
                action=ActionHint(kind="no_action", params={}),
            )
        )
        return SuggestionsResp(target="pod_cpu", key=key, suggestions=suggestions, meta=meta)

    severity: Literal["info", "warning", "critical"] = "warning"
    if peak_ratio >= 1.0:
        severity = "critical"

    # 无法定位 Deployment：只能给排查建议
    if controller_kind != "ReplicaSet" or deployment_name == "unknown":
        suggestions.append(
            SuggestionItem(
                severity=severity,
                title="预测显示 Pod CPU 持续高负载，但无法定位 Deployment 进行动作",
                evidence={
                    "pod": key,
                    "controller_kind": controller_kind,
                    "deployment_name": deployment_name,
                    "limit_mcpu": round(limit_mcpu, 2),
                    "peak_mcpu": round(peak_mcpu, 2),
                    "peak_ratio": round(peak_ratio, 3),
                    "sustain_over_minutes": sustain_over,
                },
                rationale="只有由 Deployment/ReplicaSet 管理的 Pod 才能扩容/统一调资源。",
                action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
            )
        )
        return SuggestionsResp(target="pod_cpu", key=key, suggestions=suggestions, meta=meta)

    # ===================== 热点识别：TopK 占比过高 或 少副本明显超限 -> tune 优先 =====================
    peer_usages = _extract_pod_cpu_usages_mcpu(meta)
    hotspot_top1_share_th = _to_float(meta.get("hotspot_top1_share_threshold"), 0.60)
    hotspot_topk_share_th = _to_float(meta.get("hotspot_topk_share_threshold"), 0.80)
    hotspot_topk_k = _to_int(meta.get("hotspot_topk_k"), 2)

    top1_share = _calc_topk_share(peer_usages, k=1)
    topk_share = _calc_topk_share(peer_usages, k=hotspot_topk_k)

    hotspot_by_share = bool(peer_usages) and (
        top1_share >= hotspot_top1_share_th or topk_share >= hotspot_topk_share_th
    )
    # 关键：你当前副本=1，这个分支能让你直接看到 tune
    hotspot_by_throttle = (current_replicas <= 2) and (peak_ratio >= 1.0)

    if hotspot_by_share or hotspot_by_throttle:
        # 资源调整目标：把 cpu_limit 提到 “预测峰值 / safe_high” 给余量
        safe_high_eff = max(float(safe_high), 0.01)
        target_cpu_limit_m = int(math.ceil(float(peak_mcpu) / safe_high_eff))
        target_cpu_limit_m = int(max(target_cpu_limit_m, int(math.ceil(limit_mcpu))))

        max_cpu_limit_m = _to_int(meta.get("max_cpu_limit_m"), 4000)
        target_cpu_limit_m = int(min(target_cpu_limit_m, max_cpu_limit_m))

        req_ratio = _to_float(meta.get("cpu_request_ratio"), 0.70)
        req_ratio = max(0.01, min(req_ratio, 1.0))
        target_cpu_request_m = int(math.ceil(float(target_cpu_limit_m) * req_ratio))

        suggestions.append(
            SuggestionItem(
                severity=severity,
                title="检测到热点/少副本超限，建议优先调整 Deployment 资源而非扩容副本",
                evidence={
                    "pod": key,
                    "deployment": f"{namespace}/{deployment_name}",
                    "current_replicas": current_replicas or None,
                    "peer_pods_cpu_usages_mcpu": peer_usages[:50],
                    "top1_share": round(top1_share, 3),
                    "topk_share": round(topk_share, 3),
                    "hotspot_top1_share_threshold": hotspot_top1_share_th,
                    "hotspot_topk_share_threshold": hotspot_topk_share_th,
                    "hotspot_topk_k": hotspot_topk_k,
                    "limit_mcpu": round(limit_mcpu, 2),
                    "unit": unit,
                    "peak_mcpu": round(peak_mcpu, 2),
                    "peak_ratio": round(peak_ratio, 3),
                    "threshold_ratio": threshold_ratio,
                    "sustain_over_minutes": sustain_over,
                    "required_sustain_minutes": sustain_minutes,
                    "safe_high": safe_high,
                    "target_cpu_limit_m": target_cpu_limit_m,
                    "target_cpu_request_m": target_cpu_request_m,
                    "max_cpu_limit_m": max_cpu_limit_m,
                    "reason": "hotspot_by_share" if hotspot_by_share else "hotspot_by_throttle",
                },
                rationale="扩容副本只有在流量能被均匀分摊时才有效；热点/少副本超限场景下，优先提高资源上限更直接。",
                action=ActionHint(
                    kind="tune_requests_limits",
                    params={
                        "scope": "deployment",
                        "namespace": namespace,
                        "name": deployment_name,
                        # ✅ 对齐前后端：用 cpu_*_m（millicores）
                        "cpu_limit_m": target_cpu_limit_m,
                        "cpu_request_m": target_cpu_request_m,
                        "reason": "hotspot_or_throttle",
                        "policy_used": "resource_linear" if scale_policy == "linear" else "resource_stair",
                    },
                ),
            )
        )
        return SuggestionsResp(target="pod_cpu", key=key, suggestions=suggestions, meta=meta)

    # ===================== 扩容策略计算 =====================
    replicas_delta = 0
    policy_used: ScalePolicy = scale_policy

    max_delta = 10
    max_replicas = 50
    linear_reason: Optional[str] = None
    target_replicas: Optional[int] = None
    est_ratio_after: Optional[float] = None

    if scale_policy == "linear" and current_replicas > 0:
        rs = calc_linear_target_replicas(
            current_replicas=current_replicas,
            peak_ratio=peak_ratio,
            safe_low=safe_low,
            safe_high=safe_high,
            min_replicas=max(1, current_replicas),
            max_replicas=max_replicas,
            allow_scale_down=False,
        )
        linear_reason = rs.reason
        target_replicas = rs.target_replicas
        est_ratio_after = rs.est_ratio_after

        if rs.ok and rs.scale_up and target_replicas and target_replicas > current_replicas:
            raw_delta = int(target_replicas - current_replicas)
            replicas_delta = max(0, raw_delta)
            replicas_delta = min(replicas_delta, int(max_delta))
        else:
            policy_used = "stair"

    if policy_used == "stair":
        replicas_delta = _stair_replicas_delta(peak_ratio=peak_ratio, high_threshold_ratio=high_threshold_ratio)

    if replicas_delta <= 0:
        suggestions.append(
            SuggestionItem(
                severity="warning",
                title="预测显示高负载，但扩容增量计算为 0（数据不足或已足够）",
                evidence={
                    "pod": key,
                    "deployment": f"{namespace}/{deployment_name}",
                    "scale_policy": scale_policy,
                    "policy_used": policy_used,
                    "current_replicas": current_replicas or None,
                    "limit_mcpu": round(limit_mcpu, 2),
                    "peak_mcpu": round(peak_mcpu, 2),
                    "peak_ratio": round(peak_ratio, 3),
                    "safe_low": safe_low,
                    "safe_high": safe_high,
                    "linear_reason": linear_reason,
                    "target_replicas": target_replicas,
                    "est_ratio_after": est_ratio_after,
                    "max_delta": max_delta,
                    "max_replicas": max_replicas,
                },
                rationale="线性策略可能认为当前副本数已满足安全目标，或缺少 current_replicas；也可能被限幅/上限约束。",
                action=ActionHint(kind="no_action", params={}),
            )
        )
        return SuggestionsResp(target="pod_cpu", key=key, suggestions=suggestions, meta=meta)

    suggestions.append(
        SuggestionItem(
            severity=severity,
            title=f"建议扩容 Deployment（+{replicas_delta}）以缓解 Pod CPU 持续高负载",
            evidence={
                "pod": key,
                "deployment": f"{namespace}/{deployment_name}",
                "scale_policy": scale_policy,
                "policy_used": policy_used,
                "current_replicas": current_replicas or None,
                "replicas_delta": replicas_delta,
                "limit_mcpu": round(limit_mcpu, 2),
                "unit": unit,
                "peak_mcpu": round(peak_mcpu, 2),
                "peak_ratio": round(peak_ratio, 3),
                "threshold_ratio": threshold_ratio,
                "high_threshold_ratio": high_threshold_ratio,
                "sustain_over_minutes": sustain_over,
                "required_sustain_minutes": sustain_minutes,
                "safe_low": safe_low,
                "safe_high": safe_high,
                "linear_reason": linear_reason,
                "target_replicas": target_replicas,
                "est_ratio_after": est_ratio_after,
                "max_delta": max_delta,
                "max_replicas": max_replicas,
            },
            rationale="预测显示未来一段时间 CPU 将持续高于阈值，扩容能摊薄单副本压力。",
            action=ActionHint(
                kind="scale_deployment",
                params={"replicas_delta": replicas_delta},
            ),
        )
    )

    return SuggestionsResp(target="pod_cpu", key=key, suggestions=suggestions, meta=meta)
