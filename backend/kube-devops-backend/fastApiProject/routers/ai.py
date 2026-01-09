# routers/ai.py
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, Literal

from services.ai.forecast_cpu import get_cpu_history, get_cpu_forecast
from services.ai.forecast_mem import get_mem_history, get_mem_forecast
from services.ai.forecast_pod_cpu import get_pod_cpu_history, get_pod_cpu_forecast

from services.ai.suggest import build_suggestions
from services.ai.assistant import assistant_chat
from services.ops.actions import apply_action
from services.ops.schemas import ApplyActionReq, ApplyActionResp

from services.ai.schemas import (
    CpuHistoryResp,
    CpuForecastResp,
    MemHistoryResp,
    MemForecastResp,
    PodCpuHistoryResp,
    PodCpuForecastResp,
    SuggestionsResp,
    AnomalyResp,
    AssistantChatReq,
    AssistantChatResp,
)

router = APIRouter(prefix="/api/ai", tags=["AI"])

Target = Literal["node_cpu", "node_mem", "pod_cpu"]
ScalePolicy = Literal["stair", "linear"]


# ----------- helpers: 兼容 minutes/horizon 旧参数 -----------
def _pick_history_minutes(history_minutes: Optional[int], minutes: Optional[int], default: int) -> int:
    return int(history_minutes if history_minutes is not None else (minutes if minutes is not None else default))


def _pick_horizon_minutes(horizon_minutes: Optional[int], horizon: Optional[int], default: int) -> int:
    return int(horizon_minutes if horizon_minutes is not None else (horizon if horizon is not None else default))


# ========================= 节点 CPU =========================
@router.get("/cpu/history", response_model=CpuHistoryResp)
def cpu_history(
    node: str = Query(..., description="node name, e.g. k3s-worker-1"),
    history_minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60, description="history window minutes"),
    minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60, description="(compat) history window minutes"),
    step: int = Query(60, ge=5, le=3600, description="seconds"),
    promql: Optional[str] = Query(None, description="override promql if needed"),
):
    try:
        hm = _pick_history_minutes(history_minutes, minutes, default=240)
        return get_cpu_history(node=node, minutes=hm, step=step, promql=promql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"cpu_history failed: {e}")


@router.get("/cpu/forecast", response_model=CpuForecastResp)
def cpu_forecast(
    node: str = Query(..., description="node name"),
    history_minutes: Optional[int] = Query(None, ge=30, le=7 * 24 * 60, description="history window minutes"),
    horizon_minutes: Optional[int] = Query(None, ge=15, le=24 * 60, description="forecast horizon minutes"),
    # 兼容旧参数名
    minutes: Optional[int] = Query(None, ge=30, le=7 * 24 * 60, description="(compat) history window minutes"),
    horizon: Optional[int] = Query(None, ge=15, le=24 * 60, description="(compat) forecast horizon minutes"),
    step: int = Query(60, ge=5, le=3600, description="seconds"),
    cache_ttl: int = Query(300, ge=0, le=3600, description="cache ttl seconds"),
    promql: Optional[str] = Query(None, description="override promql if needed"),
):
    try:
        hm = _pick_history_minutes(history_minutes, minutes, default=240)
        hz = _pick_horizon_minutes(horizon_minutes, horizon, default=120)
        return get_cpu_forecast(
            node=node,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl,
            promql=promql,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"cpu_forecast failed: {e}")


# ========================= 节点 Mem =========================
@router.get("/mem/history", response_model=MemHistoryResp)
def mem_history(
    node: str = Query(...),
    history_minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60),
    minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60, description="(compat)"),
    step: int = Query(60, ge=1, le=3600),
    promql: Optional[str] = Query(None),
):
    try:
        hm = _pick_history_minutes(history_minutes, minutes, default=240)
        return get_mem_history(node=node, minutes=hm, step=step, promql=promql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"mem_history failed: {e}")


@router.get("/mem/forecast", response_model=MemForecastResp)
def mem_forecast(
    node: str = Query(...),
    history_minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60),
    horizon_minutes: Optional[int] = Query(None, ge=1, le=24 * 60),
    minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60, description="(compat)"),
    horizon: Optional[int] = Query(None, ge=1, le=24 * 60, description="(compat)"),
    step: int = Query(60, ge=1, le=3600),
    cache_ttl: int = Query(300, ge=0, le=3600),
    promql: Optional[str] = Query(None),
):
    try:
        hm = _pick_history_minutes(history_minutes, minutes, default=240)
        hz = _pick_horizon_minutes(horizon_minutes, horizon, default=120)
        return get_mem_forecast(
            node=node,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl,
            promql=promql,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"mem_forecast failed: {e}")


# ========================= Pod CPU =========================
@router.get("/pod/cpu/history", response_model=PodCpuHistoryResp)
def pod_cpu_history(
    namespace: str = Query(...),
    pod: str = Query(...),
    history_minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60),
    minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60, description="(compat)"),
    step: int = Query(60, ge=1, le=3600),
    promql: Optional[str] = Query(None),
):
    try:
        hm = _pick_history_minutes(history_minutes, minutes, default=240)
        return get_pod_cpu_history(namespace=namespace, pod=pod, minutes=hm, step=step, promql=promql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pod_cpu_history failed: {e}")


@router.get("/pod/cpu/forecast", response_model=PodCpuForecastResp)
def pod_cpu_forecast(
    namespace: str = Query(...),
    pod: str = Query(...),
    history_minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60),
    horizon_minutes: Optional[int] = Query(None, ge=1, le=24 * 60),
    minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60, description="(compat)"),
    horizon: Optional[int] = Query(None, ge=1, le=24 * 60, description="(compat)"),
    step: int = Query(60, ge=1, le=3600),
    cache_ttl: int = Query(300, ge=0, le=3600),
    promql: Optional[str] = Query(None),
):
    try:
        hm = _pick_history_minutes(history_minutes, minutes, default=240)
        hz = _pick_horizon_minutes(horizon_minutes, horizon, default=120)
        return get_pod_cpu_forecast(
            namespace=namespace,
            pod=pod,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl,
            promql=promql,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pod_cpu_forecast failed: {e}")


# ===== 智能建议（规则+异常+可选LLM总结）=====
@router.get("/suggestions", response_model=SuggestionsResp)
def suggestions(
    target: Target = Query(...),
    node: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    pod: Optional[str] = Query(None),
    history_minutes: int = Query(240, ge=30, le=7 * 24 * 60),
    horizon_minutes: int = Query(120, ge=15, le=24 * 60),
    step: int = Query(60, ge=5, le=3600),
    threshold: float = Query(85.0, ge=1.0, le=100.0),
    sustain_minutes: int = Query(15, ge=1, le=120),
    use_llm: bool = Query(True),
    # ✅ 阶段3.1：扩容策略参数（只对 pod_cpu 的扩容建议有意义）
    scale_policy: ScalePolicy = Query("stair"),
    safe_low: float = Query(0.6, ge=0.1, le=1.2),
    safe_high: float = Query(0.7, ge=0.1, le=1.2),
):
    try:
        out = build_suggestions(
            target=target,
            node=node,
            namespace=namespace,
            pod=pod,
            history_minutes=history_minutes,
            horizon_minutes=horizon_minutes,
            step=step,
            threshold=threshold,
            sustain_minutes=sustain_minutes,
            use_llm=use_llm,
            scale_policy=scale_policy,
            safe_low=safe_low,
            safe_high=safe_high,
        )
        return out["suggestions"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"suggestions failed: {e}")


@router.get("/anomalies", response_model=AnomalyResp)
def anomalies(
    target: Target = Query(...),
    node: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    pod: Optional[str] = Query(None),
    history_minutes: int = Query(240, ge=30, le=7 * 24 * 60),
    horizon_minutes: int = Query(120, ge=15, le=24 * 60),
    step: int = Query(60, ge=5, le=3600),
):
    try:
        out = build_suggestions(
            target=target,
            node=node,
            namespace=namespace,
            pod=pod,
            history_minutes=history_minutes,
            horizon_minutes=horizon_minutes,
            step=step,
            threshold=85.0,
            sustain_minutes=15,
            use_llm=False,
            # anomalies 也用同一套默认策略（不影响结果，但避免 build_suggestions 里假设参数存在）
            scale_policy="stair",
            safe_low=0.6,
            safe_high=0.7,
        )
        return out["anomalies"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"anomalies failed: {e}")


# ===== 悬浮球/智能助手：Chat =====
@router.post("/assistant/chat", response_model=AssistantChatResp)
def assistant_chat_api(req: AssistantChatReq):
    try:
        return assistant_chat(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"assistant_chat failed: {e}")


def _map_action_hint_to_ops_req(
    kind: str,
    params: dict,
    target: dict,
    dry_run: bool,
) -> ApplyActionReq:
    k = (kind or "").lower()

    # 统一 target 字段：namespace/name/pod
    ns = target.get("namespace") or "default"

    # 1) 扩容 deployment
    if k == "scale_deployment":
        name = target.get("name")
        if not name:
            raise ValueError("target.name (deployment) required for scale_deployment")
        return ApplyActionReq(
            action="SCALE_DEPLOYMENT",
            target={"namespace": ns, "name": name},
            params=params or {},
            dry_run=dry_run,
        )

    # 2) 重启 deployment（rollout restart）
    if k == "restart_deployment":
        name = target.get("name")
        if not name:
            raise ValueError("target.name (deployment) required for restart_deployment")
        return ApplyActionReq(
            action="RESTART_DEPLOYMENT",
            target={"namespace": ns, "name": name},
            params=params or {},
            dry_run=dry_run,
        )

    # 3) 重启 pod：用 delete_pod 实现
    if k in ("restart_pod", "delete_pod"):
        pod = target.get("pod") or target.get("name")
        if not pod:
            raise ValueError("target.pod required for restart_pod/delete_pod")
        return ApplyActionReq(
            action="DELETE_POD",
            target={"namespace": ns, "pod": pod},
            params=params or {},
            dry_run=dry_run,
        )

    # 4) 调整资源（Deployment 级别 patch spec.template.resources）
    if k == "tune_requests_limits":
        name = target.get("name")
        if not name:
            raise ValueError("target.name (deployment) required for tune_requests_limits")
        return ApplyActionReq(
            action="TUNE_REQUESTS_LIMITS",
            target={"namespace": ns, "name": name},
            params=params or {},
            dry_run=dry_run,
        )

    # 其他 kind：先不执行（但可以让前端仅展示“操作指南”）
    raise ValueError(f"ActionHint.kind not executable yet: {kind}")


@router.post("/execute", response_model=ApplyActionResp)
def execute_suggestion(
    target: Target = Query(...),
    node: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    pod: Optional[str] = Query(None),
    history_minutes: int = Query(240, ge=30, le=7 * 24 * 60),
    horizon_minutes: int = Query(120, ge=15, le=24 * 60),
    step: int = Query(60, ge=5, le=3600),
    threshold: float = Query(85.0, ge=1.0, le=100.0),
    sustain_minutes: int = Query(15, ge=1, le=120),
    scale_policy: ScalePolicy = Query("stair"),
    safe_low: float = Query(0.6, ge=0.1, le=1.2),
    safe_high: float = Query(0.7, ge=0.1, le=1.2),
    suggestion_index: int = Query(0, ge=0),
    expected_kind: Optional[str] = Query(None, description="frontend expected action kind to prevent index drift"),
    dry_run: bool = Query(True),
    exec_namespace: str = Query("default"),
    exec_name: Optional[str] = Query(None, description="deployment name when scaling/restart/tune"),
    exec_pod: Optional[str] = Query(None, description="pod name when restart_pod/delete_pod"),

    # ✅ 弹窗覆盖：scale
    exec_replicas: Optional[int] = Query(None, ge=0, description="override final replicas for scale_deployment"),
    exec_replicas_delta: Optional[int] = Query(None, ge=0, description="override replicas_delta for scale_deployment"),

    # ✅ 兼容前端当前传参（你前端发的是 replicas / cpu_request_m 这一套）
    replicas: Optional[int] = Query(None, ge=0, description="(compat) override final replicas"),
    replicas_delta: Optional[int] = Query(None, ge=0, description="(compat) override replicas_delta"),

    cpu_request_m: Optional[float] = Query(None, ge=0, description="(compat) override cpu_request_m"),
    cpu_limit_m: Optional[float] = Query(None, ge=0, description="(compat) override cpu_limit_m"),
    mem_request_mb: Optional[float] = Query(None, ge=0, description="(compat) override mem_request_mb"),
    mem_limit_mb: Optional[float] = Query(None, ge=0, description="(compat) override mem_limit_mb"),

        # ✅ 弹窗覆盖：tune（数值形式）
    exec_cpu_request_m: Optional[float] = Query(None, ge=0, description="override cpu_request_m"),
    exec_cpu_limit_m: Optional[float] = Query(None, ge=0, description="override cpu_limit_m"),
    exec_mem_request_mb: Optional[float] = Query(None, ge=0, description="override mem_request_mb"),
    exec_mem_limit_mb: Optional[float] = Query(None, ge=0, description="override mem_limit_mb"),


    # ✅ （可选）字符串形式：你前端如果不传可以不管
    exec_cpu_request_str: Optional[str] = Query(None, description='override cpu request string, e.g. "200m"'),
    exec_cpu_limit_str: Optional[str] = Query(None, description='override cpu limit string, e.g. "500m"'),
    exec_mem_request_str: Optional[str] = Query(None, description='override mem request string, e.g. "256Mi"'),
    exec_mem_limit_str: Optional[str] = Query(None, description='override mem limit string, e.g. "512Mi"'),
):
    try:
        out = build_suggestions(
            target=target,
            node=node,
            namespace=namespace,
            pod=pod,
            history_minutes=history_minutes,
            horizon_minutes=horizon_minutes,
            step=step,
            threshold=threshold,
            sustain_minutes=sustain_minutes,
            use_llm=False,
            scale_policy=scale_policy,
            safe_low=safe_low,
            safe_high=safe_high,
        )

        sug = out["suggestions"]
        if not sug.suggestions or suggestion_index >= len(sug.suggestions):
            raise ValueError("suggestion_index out of range")

        item = sug.suggestions[suggestion_index]
        hint = item.action
        if not hint:
            raise ValueError("selected suggestion has no action hint")

        k = (hint.kind or "").lower()
        # ✅ 防止 index 漂移导致执行了另一条动作（比如 UI 是 tune，执行却变 scale）
        if expected_kind:
            ek = (expected_kind or "").lower()
            if ek != k:
                raise ValueError(f"action kind changed after rebuild: expected={ek}, got={k}. please re-generate suggestions.")


        merged_params = dict(hint.params or {})

        if k == "scale_deployment":
            # ✅ exec_* 优先；否则吃 compat replicas/replicas_delta
            final_r = exec_replicas if exec_replicas is not None else replicas
            delta_r = exec_replicas_delta if exec_replicas_delta is not None else replicas_delta

            if final_r is not None:
                merged_params["replicas"] = int(final_r)
                merged_params.pop("replicas_delta", None)  # 避免冲突
            elif delta_r is not None:
                merged_params["replicas_delta"] = int(delta_r)

        elif k == "tune_requests_limits":
            # ✅ exec_* 优先；否则吃 compat cpu_request_m 等
            c_req = exec_cpu_request_m if exec_cpu_request_m is not None else cpu_request_m
            c_lim = exec_cpu_limit_m if exec_cpu_limit_m is not None else cpu_limit_m
            m_req = exec_mem_request_mb if exec_mem_request_mb is not None else mem_request_mb
            m_lim = exec_mem_limit_mb if exec_mem_limit_mb is not None else mem_limit_mb

            if c_req is not None:
                merged_params["cpu_request_m"] = float(c_req)
            if c_lim is not None:
                merged_params["cpu_limit_m"] = float(c_lim)
            if m_req is not None:
                merged_params["mem_request_mb"] = float(m_req)
            if m_lim is not None:
                merged_params["mem_limit_mb"] = float(m_lim)

            # 字符串形式优先级更高（如果给了就覆盖数值）
            if exec_cpu_request_str:
                merged_params["cpu_request_str"] = exec_cpu_request_str
            if exec_cpu_limit_str:
                merged_params["cpu_limit_str"] = exec_cpu_limit_str
            if exec_mem_request_str:
                merged_params["mem_request_str"] = exec_mem_request_str
            if exec_mem_limit_str:
                merged_params["mem_limit_str"] = exec_mem_limit_str


        ops_req = _map_action_hint_to_ops_req(
            kind=hint.kind,
            params=merged_params,
            target={"namespace": exec_namespace, "name": exec_name, "pod": exec_pod},
            dry_run=dry_run,
        )
        return apply_action(ops_req)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"execute suggestion failed: {e}")
