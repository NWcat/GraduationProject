# routers/ai.py
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException, Depends, Body
from pydantic import BaseModel
from typing import Optional, Literal, Union, Any, Dict

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from services.ai.forecast_cpu import get_cpu_history, get_cpu_forecast
from services.ai.forecast_mem import get_mem_history, get_mem_forecast
from services.ai.forecast_pod_cpu import get_pod_cpu_history, get_pod_cpu_forecast

from services.ai.forecast_core import compute_effective_step, get_max_points

from services.ai.cache import get_task_state, set_task_state

from services.ai.suggest import (
    build_suggestions,
    cache_suggestion_snapshot,
    get_suggestion_snapshot,
    get_suggestion_snapshot_details,
    build_llm_summary,
    record_feedback,
    get_evolution_view,
    delete_evolution,
)
from services.ai.assistant import assistant_chat
from services.ops.actions import apply_action
from services.ops.schemas import ApplyActionReq, ApplyActionResp
from routers.authz import require_user
from db.repo_ai_state import upsert_state, get_states

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
    FeedbackReq,
    FeedbackResp,
    EvolutionResp,
    EvolutionParams,
)

router = APIRouter(prefix="/api/ai", tags=["AI"])

Target = Literal["node_cpu", "node_mem", "pod_cpu"]
ScalePolicy = Literal["stair", "linear"]
TaskStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED"]

TASK_TTL_SEC = 600
_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=4)


class TaskError(BaseModel):
    detail: str


class TaskStatusResp(BaseModel):
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[TaskError] = None
    created_ts: Optional[int] = None
    deadline_ts: Optional[int] = None


# ----------- helpers: 兼容 minutes/horizon 旧参数 -----------
def _pick_history_minutes(history_minutes: Optional[int], minutes: Optional[int], default: int) -> int:
    return int(history_minutes if history_minutes is not None else (minutes if minutes is not None else default))


def _pick_horizon_minutes(horizon_minutes: Optional[int], horizon: Optional[int], default: int) -> int:
    return int(horizon_minutes if horizon_minutes is not None else (horizon if horizon is not None else default))


def _apply_step_meta(resp, history_minutes: int, step: int):
    meta = getattr(resp, "meta", None) or {}
    if not isinstance(meta, dict):
        return resp
    meta = dict(meta)
    max_points = get_max_points()
    effective_step = compute_effective_step(history_minutes, step, max_points=max_points)
    meta["requested_step"] = int(step)
    meta["effective_step"] = int(effective_step)
    meta["max_points"] = int(max_points)
    resp.meta = meta
    return resp


def _init_task_state(task_id: str) -> Dict[str, Any]:
    now = int(time.time())
    state: Dict[str, Any] = {
        "task_id": task_id,
        "status": "PENDING",
        "created_ts": now,
        "deadline_ts": now + int(TASK_TTL_SEC),
    }
    set_task_state(task_id, state, TASK_TTL_SEC)
    return state


def _update_task_state(task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    state = get_task_state(task_id) or {"task_id": task_id}
    state = dict(state)
    state.update(updates)
    set_task_state(task_id, state, TASK_TTL_SEC)
    return state


def _submit_task(task_id: str, fn):
    def _runner():
        _update_task_state(task_id, {"status": "RUNNING"})
        try:
            result = fn()
            _update_task_state(task_id, {"status": "DONE", "result": result, "error": None})
        except HTTPException as e:
            _update_task_state(
                task_id,
                {"status": "FAILED", "error": {"detail": str(e.detail or e)}},
            )
        except Exception as e:
            _update_task_state(
                task_id,
                {"status": "FAILED", "error": {"detail": str(e)}},
            )

    _TASK_EXECUTOR.submit(_runner)


def _get_task_state_for_response(task_id: str) -> Optional[Dict[str, Any]]:
    state = get_task_state(task_id)
    if not state:
        return None
    status = str(state.get("status") or "")
    deadline_ts = int(state.get("deadline_ts") or 0)
    if status in ("PENDING", "RUNNING") and deadline_ts and time.time() > deadline_ts:
        state = _update_task_state(
            task_id,
            {"status": "FAILED", "error": {"detail": "task timeout"}},
        )
    return state


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
        resp = get_cpu_history(node=node, minutes=hm, step=step, promql=promql)
        return _apply_step_meta(resp, hm, step)
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
        resp = get_cpu_forecast(
            node=node,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl,
            promql=promql,
        )
        return _apply_step_meta(resp, hm, step)
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
        resp = get_mem_history(node=node, minutes=hm, step=step, promql=promql)
        return _apply_step_meta(resp, hm, step)
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
        resp = get_mem_forecast(
            node=node,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl,
            promql=promql,
        )
        return _apply_step_meta(resp, hm, step)
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
        resp = get_pod_cpu_history(namespace=namespace, pod=pod, minutes=hm, step=step, promql=promql)
        return _apply_step_meta(resp, hm, step)
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
        resp = get_pod_cpu_forecast(
            namespace=namespace,
            pod=pod,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl,
            promql=promql,
        )
        return _apply_step_meta(resp, hm, step)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pod_cpu_forecast failed: {e}")


# ========================= Unified Forecast =========================
@router.get("/forecast", response_model=Union[CpuForecastResp, MemForecastResp, PodCpuForecastResp, TaskStatusResp])
def unified_forecast(
    target: Target = Query(...),
    node: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    pod: Optional[str] = Query(None),
    history_minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60),
    horizon_minutes: Optional[int] = Query(None, ge=1, le=24 * 60),
    minutes: Optional[int] = Query(None, ge=10, le=7 * 24 * 60, description="(compat)"),
    horizon: Optional[int] = Query(None, ge=1, le=24 * 60, description="(compat)"),
    step: int = Query(60, ge=1, le=3600),
    cache_ttl: int = Query(300, ge=0, le=3600),
    promql: Optional[str] = Query(None),
    async_mode: bool = Query(False, description="run forecast asynchronously"),
):
    hm = _pick_history_minutes(history_minutes, minutes, default=240)
    hz = _pick_horizon_minutes(horizon_minutes, horizon, default=120)

    if target == "node_cpu":
        if not node:
            raise HTTPException(status_code=400, detail="node is required for target=node_cpu")
        if hm < 30:
            raise HTTPException(status_code=400, detail="history_minutes must be >= 30 for target=node_cpu")
        if hz < 15:
            raise HTTPException(status_code=400, detail="horizon_minutes must be >= 15 for target=node_cpu")
        if step < 5:
            raise HTTPException(status_code=400, detail="step must be >= 5 for target=node_cpu")
    elif target == "node_mem":
        if not node:
            raise HTTPException(status_code=400, detail="node is required for target=node_mem")
        if hm < 10:
            raise HTTPException(status_code=400, detail="history_minutes must be >= 10 for target=node_mem")
        if hz < 1:
            raise HTTPException(status_code=400, detail="horizon_minutes must be >= 1 for target=node_mem")
    elif target == "pod_cpu":
        if not namespace or not pod:
            raise HTTPException(status_code=400, detail="namespace and pod are required for target=pod_cpu")
        if hm < 10:
            raise HTTPException(status_code=400, detail="history_minutes must be >= 10 for target=pod_cpu")
        if hz < 1:
            raise HTTPException(status_code=400, detail="horizon_minutes must be >= 1 for target=pod_cpu")
    else:
        raise HTTPException(status_code=400, detail=f"unsupported target: {target}")

    def _do_forecast():
        if target == "node_cpu":
            resp = get_cpu_forecast(
                node=node,
                minutes=hm,
                horizon=hz,
                step=step,
                cache_ttl=cache_ttl,
                promql=promql,
            )
        elif target == "node_mem":
            resp = get_mem_forecast(
                node=node,
                minutes=hm,
                horizon=hz,
                step=step,
                cache_ttl=cache_ttl,
                promql=promql,
            )
        else:
            resp = get_pod_cpu_forecast(
                namespace=namespace,
                pod=pod,
                minutes=hm,
                horizon=hz,
                step=step,
                cache_ttl=cache_ttl,
                promql=promql,
            )

        meta = resp.meta or {}
        if isinstance(meta, dict):
            meta = dict(meta)
            meta["target"] = target
            resp.meta = meta
        return _apply_step_meta(resp, hm, step)

    if async_mode:
        task_id = uuid.uuid4().hex
        state = _init_task_state(task_id)
        _submit_task(task_id, _do_forecast)
        return state

    try:
        return _do_forecast()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"unified_forecast failed: {e}")


# ===== 智能建议（规则+异常+可选LLM总结）=====
@router.get("/suggestions", response_model=Union[SuggestionsResp, TaskStatusResp])
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
    use_llm: bool = Query(False),
    # ✅ 阶段3.1：扩容策略参数（只对 pod_cpu 的扩容建议有意义）
    scale_policy: ScalePolicy = Query("stair"),
    safe_low: float = Query(0.6, ge=0.1, le=1.2),
    safe_high: float = Query(0.7, ge=0.1, le=1.2),
    async_mode: bool = Query(False, description="run suggestions asynchronously"),
):
    def _do_suggestions():
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
        sug = out["suggestions"]
        anomalies_count = len(getattr(out.get("anomalies"), "anomalies", []) or [])
        suggestion_id = cache_suggestion_snapshot(sug, anomalies_count=anomalies_count)
        sug.suggestion_id = suggestion_id
        return sug

    if async_mode:
        task_id = uuid.uuid4().hex
        state = _init_task_state(task_id)
        _submit_task(task_id, _do_suggestions)
        return state

    try:
        return _do_suggestions()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid parameters: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"suggestions failed: {e}")


@router.post("/suggestions/state")
def set_suggestion_state(
    req: Dict[str, Any] = Body(...),
    user: str = Depends(require_user),
):
    row_key = str(req.get("row_key", "")).strip()
    status = str(req.get("status", "")).strip()
    if not row_key:
        raise HTTPException(status_code=400, detail="row_key is required")
    if status not in ("read", "ignored"):
        raise HTTPException(status_code=400, detail="status must be read or ignored")
    try:
        upsert_state(user=user, row_key=row_key, status=status)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"suggestion state failed: {e}")


@router.post("/suggestions/states")
def get_suggestion_states(
    req: Dict[str, Any] = Body(...),
    user: str = Depends(require_user),
):
    row_keys = req.get("row_keys")
    if not isinstance(row_keys, list):
        raise HTTPException(status_code=400, detail="row_keys is required")
    keys = [str(k).strip() for k in row_keys if str(k).strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="row_keys is required")
    try:
        states = get_states(user=user, row_keys=keys)
        return {"states": states}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"suggestion states failed: {e}")


@router.get("/tasks/{task_id}", response_model=TaskStatusResp)
def get_task(task_id: str):
    state = _get_task_state_for_response(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="task not found or expired")
    return state


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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid parameters: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"anomalies failed: {e}")


@router.get("/suggestions/summary")
def suggestions_summary(suggestion_id: str = Query(..., description="suggestions snapshot id")):
    try:
        cached = get_suggestion_snapshot_details(suggestion_id)
        if not cached:
            raise HTTPException(
                status_code=409,
                detail="suggestion_id 已过期或无效，请重新生成建议",
            )
        sug, anomalies_count = cached
        llm_summary = build_llm_summary(sug, anomalies_count=anomalies_count)
        return {"suggestion_id": suggestion_id, "llm_summary": llm_summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"suggestions summary failed: {e}")


# ===== 悬浮球/智能助手：Chat =====
@router.post("/feedback", response_model=FeedbackResp)
def ai_feedback(req: FeedbackReq):
    try:
        result = record_feedback(
            target=req.target,
            key=req.key,
            action_kind=req.action_kind,
            outcome=req.outcome,
            detail=req.detail,
            suggestion_id=req.suggestion_id,
            ts=req.ts,
        )
        evolution = None
        evolved = bool(result.get("evolution"))
        if evolved:
            params, source, enabled = get_evolution_view(req.target, req.key)
            evolution = EvolutionResp(
                target=req.target,
                key=req.key,
                enabled=enabled,
                params=EvolutionParams(**params),
                source=source,
            )
        return FeedbackResp(
            ok=True,
            feedback_id=result.get("feedback_id"),
            evolved=evolved,
            evolution=evolution,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"feedback failed: {e}")


@router.get("/evolution", response_model=EvolutionResp)
def get_evolution(
    target: Target = Query(...),
    key: str = Query(...),
):
    try:
        params, source, enabled = get_evolution_view(target, key)
        return EvolutionResp(
            target=target,
            key=key,
            enabled=enabled,
            params=EvolutionParams(**params),
            source=source,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"get evolution failed: {e}")


@router.delete("/evolution")
def delete_evolution_key(
    target: Target = Query(...),
    key: str = Query(...),
):
    try:
        deleted = delete_evolution(target, key)
        return {"ok": True, "deleted": bool(deleted), "target": target, "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete evolution failed: {e}")


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
    suggestion_id: Optional[str] = Query(None, description="suggestions snapshot id; avoids rebuild (preferred)"),
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
        sug = None
        if suggestion_id:
            sug = get_suggestion_snapshot(suggestion_id)
            if not sug:
                raise HTTPException(
                    status_code=409,
                    detail="suggestion_id 已过期或无效，请重新生成建议",
                )
        else:
            # deprecated: rebuild suggestions on execute
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

    except HTTPException:
        raise
    except (ValueError, IndexError) as e:
        raise HTTPException(status_code=400, detail=f"invalid parameters: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"execute suggestion failed: {e}")
