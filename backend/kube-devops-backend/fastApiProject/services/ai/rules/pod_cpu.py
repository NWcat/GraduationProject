from __future__ import annotations

import math
from typing import Literal

from services.ai.schemas import SuggestionItem, ActionHint

from .registry import register_rule
from .types import (
    RuleContext,
    RuleResult,
    _get_attr,
    _max_yhat,
    _sustain_over_threshold_minutes,
    _stair_replicas_delta,
    _to_float,
    _to_int,
)


def _extract_history_mcpu(forecast) -> list[float]:
    history = _get_attr(forecast, "history", []) or []
    values: list[float] = []
    for p in history:
        if isinstance(p, dict):
            values.append(_to_float(p.get("value"), 0.0))
        else:
            values.append(_to_float(_get_attr(p, "value", 0.0), 0.0))
    return [v for v in values if v >= 0.0]


def _extract_forecast_mcpu(forecast) -> list[float]:
    points = _get_attr(forecast, "forecast", []) or []
    values: list[float] = []
    for p in points:
        if isinstance(p, dict):
            values.append(_to_float(p.get("yhat"), 0.0))
        else:
            values.append(_to_float(_get_attr(p, "yhat", 0.0), 0.0))
    return [v for v in values if v >= 0.0]


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    q = max(0.0, min(1.0, float(q)))
    data = sorted(values)
    n = len(data)
    idx = int(math.ceil(q * n)) - 1
    idx = max(0, min(n - 1, idx))
    return float(data[idx])


def _recommend_cpu_mcpu(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "p95": 0.0,
            "p99": 0.0,
            "avg": 0.0,
            "request": 0.0,
            "limit": 0.0,
        }
    avg = float(sum(values)) / max(len(values), 1)
    p95 = _percentile(values, 0.95)
    p99 = _percentile(values, 0.99)
    request = max(p95, avg * 1.2)
    limit = max(p99, request * 1.5)
    return {
        "p95": float(p95),
        "p99": float(p99),
        "avg": float(avg),
        "request": float(request),
        "limit": float(limit),
    }


def _build_resource_patch_yaml(
    *,
    workload_kind: str,
    workload_name: str,
    namespace: str,
    cpu_request_m: float,
    cpu_limit_m: float,
) -> str:
    kind = workload_kind if workload_kind in ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet") else "Workload"
    name = workload_name or "name"
    ns = namespace or "default"
    req = int(math.ceil(max(cpu_request_m, 0.0)))
    lim = int(math.ceil(max(cpu_limit_m, 0.0)))
    lines = [
        "apiVersion: apps/v1",
        f"kind: {kind}",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {ns}",
        "spec:",
        "  template:",
        "    spec:",
        "      containers:",
        "      - name: <container>",
        "        resources:",
        "          requests:",
        f"            cpu: \"{req}m\"",
        "          limits:",
        f"            cpu: \"{lim}m\"",
    ]
    return "\n".join(lines) + "\n"


def _workload_fields(meta: dict) -> dict:
    return {
        "controller_kind": str(meta.get("controller_kind") or ""),
        "controller_name": str(meta.get("controller_name") or ""),
        "workload_kind": str(meta.get("workload_kind") or "Unknown"),
        "workload_name": str(meta.get("workload_name") or "unknown"),
    }


def _is_bare_pod(controller_kind: str, workload_kind: str) -> bool:
    ck = str(controller_kind or "").strip()
    wk = str(workload_kind or "").strip()
    if not ck and (not wk or wk in ("Unknown", "None")):
        return True
    if wk in ("Unknown", "None") and ck in ("Unknown", "None", ""):
        return True
    return False


@register_rule(name="pod_cpu_base", target="pod_cpu", priority=100)
def rule_pod_cpu_base(ctx: RuleContext) -> RuleResult:
    namespace = ctx.namespace or ""
    pod = ctx.pod or ""
    key = ctx.key or f"{namespace}/{pod}"
    forecast = ctx.forecast

    observe_ratio = float(
        ctx.observe_ratio
        if ctx.observe_ratio is not None
        else (ctx.threshold_ratio if ctx.threshold_ratio is not None else 0.80)
    )
    trigger_ratio = float(
        ctx.trigger_ratio
        if ctx.trigger_ratio is not None
        else (ctx.high_threshold_ratio if ctx.high_threshold_ratio is not None else 0.90)
    )
    critical_ratio = float(ctx.critical_ratio if ctx.critical_ratio is not None else 1.00)
    if trigger_ratio < observe_ratio:
        trigger_ratio = observe_ratio
    if critical_ratio < trigger_ratio:
        critical_ratio = trigger_ratio

    meta = _get_attr(forecast, "meta", None) or {}
    points = _get_attr(forecast, "forecast", []) or []

    limit_mcpu = _to_float(meta.get("limit_mcpu"), 0.0)
    has_limit = bool(meta.get("has_limit")) if "has_limit" in meta else limit_mcpu > 0

    history_vals = _extract_history_mcpu(forecast)
    if not history_vals and not points:
        evidence = {
            "pod": key,
            "has_limit": has_limit,
            "data_points": 0,
            "rule_name": "pod_cpu_base",
            "status": "normal",
            **_workload_fields(meta),
        }
        return SuggestionItem(
            severity="info",
            title="CPU 预测正常（数据不足，需持续观测）",
            evidence=evidence,
            rationale="历史或预测数据不足，暂无法精确评估风险；建议持续观测并补齐资源配置。",
            action=ActionHint(kind="no_action", params={}),
        )

    predicted_max = _max_yhat(points)
    avg_history = float(sum(history_vals)) / max(len(history_vals), 1) if history_vals else 0.0

    rec = _recommend_cpu_mcpu(history_vals) if not has_limit else None
    base_limit = float(limit_mcpu) if limit_mcpu > 0 else float(rec["limit"]) if rec else 0.0
    observe_threshold_mcpu = float(base_limit) * float(observe_ratio) if base_limit > 0 else 0.0
    trigger_threshold_mcpu = float(base_limit) * float(trigger_ratio) if base_limit > 0 else 0.0
    critical_threshold_mcpu = float(base_limit) * float(critical_ratio) if base_limit > 0 else 0.0

    status = "normal"
    if critical_threshold_mcpu > 0 and predicted_max >= critical_threshold_mcpu:
        status = "critical"
    elif trigger_threshold_mcpu > 0 and predicted_max >= trigger_threshold_mcpu:
        status = "trigger"
    elif observe_threshold_mcpu > 0 and predicted_max >= observe_threshold_mcpu:
        status = "near"

    evidence = {
        "pod": key,
        "predicted_max_yhat_mcpu": round(predicted_max, 2),
        "avg_history_mcpu": round(avg_history, 2),
        "has_limit": has_limit,
        "rule_name": "pod_cpu_base",
        "status": status,
        **_workload_fields(meta),
    }
    if observe_threshold_mcpu > 0:
        evidence["observe_threshold_mcpu"] = round(observe_threshold_mcpu, 2)
        evidence["trigger_threshold_mcpu"] = round(trigger_threshold_mcpu, 2)
        evidence["critical_threshold_mcpu"] = round(critical_threshold_mcpu, 2)
        evidence["observe_ratio"] = round(observe_ratio, 3)
        evidence["trigger_ratio"] = round(trigger_ratio, 3)
        evidence["critical_ratio"] = round(critical_ratio, 3)
    else:
        evidence["observe_ratio"] = round(observe_ratio, 3)
        evidence["trigger_ratio"] = round(trigger_ratio, 3)
        evidence["critical_ratio"] = round(critical_ratio, 3)

    if status == "critical":
        rationale = "预测峰值已达到或超过关键阈值，存在高风险，需要尽快排查或准备扩容/限流。"
        if not has_limit:
            rationale = "预测峰值已达到或超过关键阈值，但当前未配置 CPU limit，阈值基于估算，仅供参考。"
        return SuggestionItem(
            severity="critical",
            title="CPU 预测高风险，可能突破限制",
            evidence=evidence,
            rationale=rationale,
            action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
        )

    if status == "trigger":
        rationale = "预测峰值达到触发阈值，存在超限风险，建议提前排查与评估扩容。"
        if not has_limit:
            rationale = "预测峰值达到触发阈值，但当前未配置 CPU limit，阈值基于估算，仅供参考。"
        return SuggestionItem(
            severity="warning",
            title="CPU 预测可能超阈值，建议提前准备",
            evidence=evidence,
            rationale=rationale,
            action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
        )

    if status == "near":
        rationale = "预测峰值接近观察阈值，建议持续观察以避免错过风险拐点。"
        if not has_limit:
            rationale = "预测峰值接近观察阈值，但当前未配置 CPU limit，阈值基于估算，仅供参考。"
        return SuggestionItem(
            severity="warning",
            title="CPU 预测接近阈值，建议持续观察",
            evidence=evidence,
            rationale=rationale,
            action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
        )

    rationale = "预测峰值未达到观察阈值，当前负载表现稳定。"
    if not has_limit:
        rationale = "预测峰值未达到观察阈值，但当前未配置 CPU limit，阈值基于估算，仅供参考。"
    return SuggestionItem(
        severity="info",
        title="CPU 预测正常，暂不需要调整",
        evidence=evidence,
        rationale=rationale,
        action=ActionHint(kind="no_action", params={}),
    )


@register_rule(name="pod_cpu_resources_recommend", target="pod_cpu", priority=110)
def rule_pod_cpu_resources_recommend(ctx: RuleContext) -> RuleResult:
    namespace = ctx.namespace or ""
    pod = ctx.pod or ""
    key = ctx.key or f"{namespace}/{pod}"
    forecast = ctx.forecast

    meta = _get_attr(forecast, "meta", None) or {}
    limit_mcpu = _to_float(meta.get("limit_mcpu"), 0.0)
    has_limit = bool(meta.get("has_limit")) if "has_limit" in meta else limit_mcpu > 0
    if has_limit:
        return None

    history_vals = _extract_history_mcpu(forecast)
    forecast_vals = _extract_forecast_mcpu(forecast)
    values = history_vals or forecast_vals
    data_source = "history" if history_vals else ("forecast" if forecast_vals else "none")

    rec = _recommend_cpu_mcpu(values) if values else _recommend_cpu_mcpu([])
    req_m = int(math.ceil(rec["request"]))
    lim_m = int(math.ceil(rec["limit"]))

    evidence = {
        "pod": key,
        "has_limit": False,
        "data_source": data_source,
        "recommended_request_mcpu": req_m,
        "recommended_limit_mcpu": lim_m,
        "rule_name": "pod_cpu_resources_recommend",
        **_workload_fields(meta),
    }
    if values:
        evidence["observed_p95_mcpu"] = round(rec["p95"], 2)
        evidence["observed_p99_mcpu"] = round(rec["p99"], 2)

    controller_kind = str(meta.get("controller_kind") or "")
    workload_kind = str(meta.get("workload_kind") or "Unknown")
    workload_name = str(meta.get("workload_name") or "unknown")
    deployment_name = str(meta.get("deployment_name") or "unknown")
    is_bare = _is_bare_pod(controller_kind, workload_kind)
    is_deployment = workload_kind == "Deployment"

    title = "未配置 CPU limit，建议补齐 requests/limits"
    rationale = "该建议用于补齐资源配置，不代表负载异常。"
    action_kind: Literal[
        "tune_requests_limits",
        "no_action",
        "investigate_logs",
    ] = "tune_requests_limits" if req_m > 0 and lim_m > 0 else "no_action"

    if not is_deployment:
        if is_bare:
            rationale = "当前为裸 Pod，暂不支持一键执行；建议改为 Deployment 或手工应用 patch_yaml。"
        else:
            rationale = "当前控制器暂不支持一键执行；建议改为 Deployment 或手工应用 patch_yaml。"
        action_kind = "no_action"
        evidence["patch_yaml"] = _build_resource_patch_yaml(
            workload_kind=workload_kind,
            workload_name=workload_name,
            namespace=namespace,
            cpu_request_m=req_m,
            cpu_limit_m=lim_m,
        )
    tune_params = (
        {
            "namespace": namespace,
            "name": workload_name,
            "cpu_request_m": req_m,
            "cpu_limit_m": lim_m,
            "reason": "missing_limit_recommend",
        }
        if action_kind == "tune_requests_limits"
        else {}
    )

    if workload_kind == "Deployment" and deployment_name != "unknown":
        return SuggestionItem(
            severity="warning",
            title=title,
            evidence={**evidence, "deployment": f"{namespace}/{deployment_name}"},
            rationale=rationale,
            action=ActionHint(
                kind=action_kind,
                params={
                    "scope": "deployment",
                    "namespace": namespace,
                    "name": deployment_name,
                    "cpu_request_m": req_m,
                    "cpu_limit_m": lim_m,
                    "reason": "missing_limit_recommend",
                }
                if action_kind == "tune_requests_limits"
                else {},
            ),
        )

    if action_kind == "tune_requests_limits":
        evidence["patch_yaml"] = _build_resource_patch_yaml(
            workload_kind=workload_kind,
            workload_name=workload_name,
            namespace=namespace,
            cpu_request_m=req_m,
            cpu_limit_m=lim_m,
        )

    return SuggestionItem(
        severity="warning",
        title=title,
        evidence=evidence,
        rationale=rationale,
        action=ActionHint(kind=action_kind, params=tune_params),
    )


@register_rule(name="pod_cpu_triggered", target="pod_cpu", priority=120)
def rule_pod_cpu_triggered(ctx: RuleContext) -> RuleResult:
    namespace = ctx.namespace or ""
    pod = ctx.pod or ""
    key = ctx.key or f"{namespace}/{pod}"
    forecast = ctx.forecast

    observe_ratio = float(
        ctx.observe_ratio
        if ctx.observe_ratio is not None
        else (ctx.threshold_ratio if ctx.threshold_ratio is not None else 0.80)
    )
    trigger_ratio = float(
        ctx.trigger_ratio
        if ctx.trigger_ratio is not None
        else (ctx.high_threshold_ratio if ctx.high_threshold_ratio is not None else 0.90)
    )
    critical_ratio = float(ctx.critical_ratio if ctx.critical_ratio is not None else 1.00)
    if trigger_ratio < observe_ratio:
        trigger_ratio = observe_ratio
    if critical_ratio < trigger_ratio:
        critical_ratio = trigger_ratio

    sustain_minutes = int(ctx.sustain_minutes if ctx.sustain_minutes is not None else 10)

    meta = _get_attr(forecast, "meta", None) or {}
    points = _get_attr(forecast, "forecast", []) or []
    step = _to_int(_get_attr(forecast, "step", 60), 60)

    limit_mcpu = _to_float(meta.get("limit_mcpu"), 0.0)
    has_limit = bool(meta.get("has_limit")) if "has_limit" in meta else limit_mcpu > 0

    history_vals = _extract_history_mcpu(forecast)
    if not history_vals and not points:
        return None

    rec = _recommend_cpu_mcpu(history_vals) if not has_limit else None
    base_limit = float(limit_mcpu) if limit_mcpu > 0 else float(rec["limit"]) if rec else 0.0
    if base_limit <= 0:
        return None

    predicted_max = _max_yhat(points)
    trigger_threshold_mcpu = float(base_limit) * float(trigger_ratio)
    critical_threshold_mcpu = float(base_limit) * float(critical_ratio)
    sustain_over = _sustain_over_threshold_minutes(points, trigger_threshold_mcpu, step)
    trigger = predicted_max >= trigger_threshold_mcpu or sustain_over >= int(sustain_minutes)
    if not trigger:
        return None

    peak_ratio = float(predicted_max) / max(float(base_limit), 1.0)
    severity: Literal["info", "warning", "critical"] = "warning"
    if predicted_max >= critical_threshold_mcpu:
        severity = "critical"

    workload_kind = str(meta.get("workload_kind") or "Unknown")
    workload_name = str(meta.get("workload_name") or "unknown")
    deployment_name = str(meta.get("deployment_name") or "unknown")

    evidence = {
        "pod": key,
        "predicted_max_yhat_mcpu": round(predicted_max, 2),
        "trigger_threshold_mcpu": round(trigger_threshold_mcpu, 2),
        "critical_threshold_mcpu": round(critical_threshold_mcpu, 2),
        "sustain_over_minutes": int(sustain_over),
        "required_sustain_minutes": int(sustain_minutes),
        "peak_ratio": round(peak_ratio, 3),
        "has_limit": has_limit,
        "observe_ratio": round(observe_ratio, 3),
        "trigger_ratio": round(trigger_ratio, 3),
        "critical_ratio": round(critical_ratio, 3),
        "rule_name": "pod_cpu_triggered",
        **_workload_fields(meta),
    }
    if not has_limit and rec:
        evidence["recommended_limit_mcpu"] = int(math.ceil(rec["limit"]))

    replicas_delta = _stair_replicas_delta(peak_ratio=peak_ratio, high_threshold_ratio=trigger_ratio)

    if workload_kind == "Deployment" and deployment_name != "unknown":
        if replicas_delta <= 0:
            return SuggestionItem(
                severity=severity,
                title="CPU 预测触发阈值，建议先排查负载来源",
                evidence=evidence,
                rationale="预测峰值或持续高负载达到触发条件，但扩容收益有限，建议先排查负载来源。",
                action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
            )

        return SuggestionItem(
            severity=severity,
            title="CPU 预测触发阈值，建议扩容",
            evidence={**evidence, "deployment": f"{namespace}/{deployment_name}", "replicas_delta": replicas_delta},
            rationale="预测峰值或持续高负载达到触发条件，扩容可缓解单副本压力。",
            action=ActionHint(kind="scale_deployment", params={"replicas_delta": replicas_delta}),
        )

    if workload_kind == "StatefulSet" and workload_name != "unknown":
        return SuggestionItem(
            severity=severity,
            title="CPU 预测触发阈值，建议手工扩容",
            evidence=evidence,
            rationale="预测峰值或持续高负载达到触发条件，但当前不支持一键扩容。",
            action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
        )

    if workload_kind == "DaemonSet":
        return SuggestionItem(
            severity=severity,
            title="CPU 预测触发阈值，建议排查或限流",
            evidence=evidence,
            rationale="DaemonSet 不支持扩容副本，建议排查负载来源或考虑限流。",
            action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
        )

    return SuggestionItem(
        severity=severity,
        title="CPU 预测触发阈值，建议排查",
        evidence=evidence,
        rationale="预测峰值或持续高负载达到触发条件，但暂无法定位可扩容工作负载。",
        action=ActionHint(kind="investigate_logs", params={"namespace": namespace, "pod": pod}),
    )
