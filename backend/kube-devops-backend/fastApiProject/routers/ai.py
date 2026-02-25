# routers/ai.py
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException, Depends, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Literal, Union, Any, Dict

import time
from datetime import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor

from services.ai.forecast_cpu import get_cpu_history, get_cpu_forecast
from services.ai.forecast_mem import get_mem_history, get_mem_forecast
from services.ai.forecast_pod_cpu import get_pod_cpu_history, get_pod_cpu_forecast

from services.ai.forecast_core import compute_effective_step, get_max_points

from db.tasks.repo import create_task, update_task_status, get_task as get_task_row
from db.alerts.repo import normalize_fingerprint, upsert_alert
from services.notification.feishu_client import push_alert_async

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
from services.ops.audit import log_action
from services.ops.schemas import ApplyActionReq, ApplyActionResp
from routers.authz import require_user
from db.ai.state_repo import upsert_state, get_states
from db.ops.actions_repo import get_last_ai_action_ts, count_ai_actions_since
from services.ops.runtime_config import get_value

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
TaskStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED", "UNKNOWN"]

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


def _ai_to_task_status(status: str) -> str:
    s = str(status or "").upper()
    if s == "DONE":
        return "SUCCESS"
    return s or "PENDING"


def _task_to_ai_status(status: str) -> str:
    s = str(status or "").upper()
    if s == "SUCCESS":
        return "DONE"
    return s or "PENDING"


def _cfg_int(key: str, default: int) -> int:
    v, _src = get_value(key)
    try:
        return int(v)
    except Exception:
        return int(default)


def _cfg_str(key: str, default: str) -> str:
    v, _src = get_value(key)
    s = (str(v) if v is not None else "").strip()
    return s if s else str(default)


def _day_start_ts() -> int:
    now = datetime.now()
    return int(datetime(year=now.year, month=now.month, day=now.day).timestamp())


def _action_type_from_kind(kind: str) -> str:
    k = str(kind or "").lower()
    if k in ("scale_deployment", "scale_hpa", "add_node"):
        return "scale"
    if k in ("tune_requests_limits",):
        return "tune_resources"
    if k in ("restart_deployment", "restart_pod", "delete_pod"):
        return "ops"
    return "alert_only"


def _build_forbid_payload(
    *,
    status_code: int,
    reason: str,
    action: str,
    dry_run: bool,
    cooldown_remaining: int = 0,
    limit_remaining: int = 0,
) -> Dict[str, Any]:
    payload = ApplyActionResp(
        ok=False,
        action=action or "FORBID",
        dry_run=bool(dry_run),
        detail=str(reason or ""),
        data={},
        forbid=True,
        forbid_reason=str(reason or ""),
        cooldown_remaining=int(cooldown_remaining or 0),
        limit_remaining=int(limit_remaining or 0),
        planned_action=None,
        evidence_snapshot=None,
    )
    return payload.model_dump()


def _forbid_response(
    *,
    status_code: int,
    reason: str,
    action: str,
    dry_run: bool,
    cooldown_remaining: int = 0,
    limit_remaining: int = 0,
) -> JSONResponse:
    payload = _build_forbid_payload(
        status_code=status_code,
        reason=reason,
        action=action,
        dry_run=dry_run,
        cooldown_remaining=cooldown_remaining,
        limit_remaining=limit_remaining,
    )
    return JSONResponse(status_code=int(status_code), content=payload)


def _build_object_key(
    *,
    target: str,
    node: Optional[str],
    namespace: Optional[str],
    pod: Optional[str],
    exec_namespace: Optional[str],
    exec_name: Optional[str],
    exec_pod: Optional[str],
    evidence: Optional[Dict[str, Any]],
) -> str:
    if str(target) in ("node_cpu", "node_mem"):
        n = (node or "").strip()
        return n if n else "node"
    if str(target) == "pod_cpu":
        ns = (namespace or exec_namespace or "default").strip() or "default"
        p = (pod or exec_pod or "").strip()
        return f"{ns}/{p}" if p else ns
    ev = evidence or {}
    duid = str(ev.get("deployment_uid") or "")
    if duid:
        ns = (exec_namespace or namespace or "default").strip() or "default"
        return f"{ns}/{duid}"
    ns = (exec_namespace or namespace or "default").strip() or "default"
    name = (exec_name or "").strip()
    return f"{ns}/{name}" if name else ns
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


def run_forecast_task(payload: Dict[str, Any]) -> Any:
    target = str(payload.get("target") or "")
    node = payload.get("node")
    namespace = payload.get("namespace")
    pod = payload.get("pod")
    history_minutes = payload.get("history_minutes")
    horizon_minutes = payload.get("horizon_minutes")
    minutes = payload.get("minutes")
    horizon = payload.get("horizon")
    step = payload.get("step")
    cache_ttl = payload.get("cache_ttl")
    promql = payload.get("promql")

    hm = _pick_history_minutes(history_minutes, minutes, default=240)
    hz = _pick_horizon_minutes(horizon_minutes, horizon, default=120)
    step = int(step or 60)

    if target == "node_cpu":
        if not node:
            raise ValueError("node is required for target=node_cpu")
        if hm < 30:
            raise ValueError("history_minutes must be >= 30 for target=node_cpu")
        if hz < 15:
            raise ValueError("horizon_minutes must be >= 15 for target=node_cpu")
        if step < 5:
            raise ValueError("step must be >= 5 for target=node_cpu")
    elif target == "node_mem":
        if not node:
            raise ValueError("node is required for target=node_mem")
        if hm < 10:
            raise ValueError("history_minutes must be >= 10 for target=node_mem")
        if hz < 1:
            raise ValueError("horizon_minutes must be >= 1 for target=node_mem")
    elif target == "pod_cpu":
        if not namespace or not pod:
            raise ValueError("namespace and pod are required for target=pod_cpu")
        if hm < 10:
            raise ValueError("history_minutes must be >= 10 for target=pod_cpu")
        if hz < 1:
            raise ValueError("horizon_minutes must be >= 1 for target=pod_cpu")
    else:
        raise ValueError(f"unsupported target: {target}")

    if target == "node_cpu":
        resp = get_cpu_forecast(
            node=node,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl if cache_ttl is not None else 300,
            promql=promql,
        )
    elif target == "node_mem":
        resp = get_mem_forecast(
            node=node,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl if cache_ttl is not None else 300,
            promql=promql,
        )
    else:
        resp = get_pod_cpu_forecast(
            namespace=namespace,
            pod=pod,
            minutes=hm,
            horizon=hz,
            step=step,
            cache_ttl=cache_ttl if cache_ttl is not None else 300,
            promql=promql,
        )

    meta = resp.meta or {}
    if isinstance(meta, dict):
        meta = dict(meta)
        meta["target"] = target
        resp.meta = meta
    return _apply_step_meta(resp, hm, step)


def run_suggestions_task(payload: Dict[str, Any]) -> Any:
    target = str(payload.get("target") or "")
    node = payload.get("node")
    namespace = payload.get("namespace")
    pod = payload.get("pod")
    history_minutes = int(payload.get("history_minutes") or 240)
    horizon_minutes = int(payload.get("horizon_minutes") or 120)
    step = int(payload.get("step") or 60)
    threshold = float(payload.get("threshold") or 85.0)
    sustain_minutes = int(payload.get("sustain_minutes") or 15)
    use_llm = bool(payload.get("use_llm") or False)
    scale_policy = str(payload.get("scale_policy") or "stair")
    safe_low = float(payload.get("safe_low") or 0.6)
    safe_high = float(payload.get("safe_high") or 0.7)

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


def run_execute_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    target = payload.get("target")
    node = payload.get("node")
    namespace = payload.get("namespace")
    pod = payload.get("pod")
    history_minutes = int(payload.get("history_minutes") or 240)
    horizon_minutes = int(payload.get("horizon_minutes") or 120)
    step = int(payload.get("step") or 60)
    threshold = float(payload.get("threshold") or 85.0)
    sustain_minutes = int(payload.get("sustain_minutes") or 15)
    scale_policy = str(payload.get("scale_policy") or "stair")
    safe_low = float(payload.get("safe_low") or 0.6)
    safe_high = float(payload.get("safe_high") or 0.7)
    suggestion_index = int(payload.get("suggestion_index") or 0)
    suggestion_id = payload.get("suggestion_id")
    expected_kind = payload.get("expected_kind")
    dry_run = bool(payload.get("dry_run") if payload.get("dry_run") is not None else True)
    confirm_text = payload.get("confirm_text")
    exec_namespace = str(payload.get("exec_namespace") or "default")
    exec_name = payload.get("exec_name")
    exec_pod = payload.get("exec_pod")

    exec_replicas = payload.get("exec_replicas")
    exec_replicas_delta = payload.get("exec_replicas_delta")
    replicas = payload.get("replicas")
    replicas_delta = payload.get("replicas_delta")

    cpu_request_m = payload.get("cpu_request_m")
    cpu_limit_m = payload.get("cpu_limit_m")
    mem_request_mb = payload.get("mem_request_mb")
    mem_limit_mb = payload.get("mem_limit_mb")

    exec_cpu_request_m = payload.get("exec_cpu_request_m")
    exec_cpu_limit_m = payload.get("exec_cpu_limit_m")
    exec_mem_request_mb = payload.get("exec_mem_request_mb")
    exec_mem_limit_mb = payload.get("exec_mem_limit_mb")

    exec_cpu_request_str = payload.get("exec_cpu_request_str")
    exec_cpu_limit_str = payload.get("exec_cpu_limit_str")
    exec_mem_request_str = payload.get("exec_mem_request_str")
    exec_mem_limit_str = payload.get("exec_mem_limit_str")

    try:
        sug = None
        if suggestion_id:
            sug = get_suggestion_snapshot(suggestion_id)
            if not sug:
                raise ValueError("suggestion_id 已过期或无效，请重新生成建议")
        else:
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
        if expected_kind:
            ek = (expected_kind or "").lower()
            if ek != k:
                raise ValueError(f"action kind changed after rebuild: expected={ek}, got={k}. please re-generate suggestions.")

        merged_params = dict(hint.params or {})

        if k == "scale_deployment":
            final_r = exec_replicas if exec_replicas is not None else replicas
            delta_r = exec_replicas_delta if exec_replicas_delta is not None else replicas_delta

            if final_r is not None:
                merged_params["replicas"] = int(final_r)
                merged_params.pop("replicas_delta", None)
            elif delta_r is not None:
                merged_params["replicas_delta"] = int(delta_r)

        elif k == "tune_requests_limits":
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

            if exec_cpu_request_str:
                merged_params["cpu_request_str"] = exec_cpu_request_str
            if exec_cpu_limit_str:
                merged_params["cpu_limit_str"] = exec_cpu_limit_str
            if exec_mem_request_str:
                merged_params["mem_request_str"] = exec_mem_request_str
            if exec_mem_limit_str:
                merged_params["mem_limit_str"] = exec_mem_limit_str

        action_type = getattr(item, "action_type", "") or _action_type_from_kind(hint.kind)
        degrade_reason = str(getattr(item, "degrade_reason", "") or "")
        evidence_snapshot = item.evidence if isinstance(item.evidence, dict) else {}
        object_key = _build_object_key(
            target=str(target),
            node=node,
            namespace=namespace,
            pod=pod,
            exec_namespace=exec_namespace,
            exec_name=exec_name,
            exec_pod=exec_pod,
            evidence=evidence_snapshot,
        )

        if not dry_run:
            expected_text = _cfg_str("AI_EXECUTE_CONFIRM_TEXT", "EXECUTE")
            if not confirm_text:
                return _build_forbid_payload(
                    status_code=400,
                    reason="真正执行需要确认文本，请传入 confirm_text 参数",
                    action=str(hint.kind or ""),
                    dry_run=dry_run,
                )
            if str(confirm_text).strip() != expected_text:
                return _build_forbid_payload(
                    status_code=400,
                    reason=f"确认文本不匹配，应为 '{expected_text}'",
                    action=str(hint.kind or ""),
                    dry_run=dry_run,
                )
            if action_type == "alert_only" or "insufficient_data" in degrade_reason:
                return _build_forbid_payload(
                    status_code=403,
                    reason="该建议数据不足，仅允许演习模式，不可真实执行",
                    action=str(hint.kind or ""),
                    dry_run=dry_run,
                )

            cooldown_minutes = _cfg_int("AI_EXECUTE_COOLDOWN_MINUTES", 10)
            daily_limit = _cfg_int("AI_EXECUTE_DAILY_LIMIT", 20)
            now_ts = int(time.time())
            if object_key and action_type:
                last_ts = get_last_ai_action_ts(object_key=object_key, action_type=action_type)
                if last_ts and cooldown_minutes > 0:
                    remain = int(cooldown_minutes * 60) - int(now_ts - last_ts)
                    if remain > 0:
                        minutes = (remain + 59) // 60
                        return _build_forbid_payload(
                            status_code=409,
                            reason=f"执行冷却中，请在 {minutes} 分钟后再试",
                            action=str(hint.kind or ""),
                            dry_run=dry_run,
                            cooldown_remaining=int(remain),
                            limit_remaining=max(0, int(daily_limit) - 1),
                        )
            if daily_limit > 0:
                used = count_ai_actions_since(ts_start=_day_start_ts())
                if used >= daily_limit:
                    return _build_forbid_payload(
                        status_code=409,
                        reason=f"今日执行次数已达限制 ({daily_limit} 次)，请明天再试",
                        action=str(hint.kind or ""),
                        dry_run=dry_run,
                        cooldown_remaining=0,
                        limit_remaining=max(0, int(daily_limit) - int(used)),
                    )

        ops_req = _map_action_hint_to_ops_req(
            kind=hint.kind,
            params=merged_params,
            target={"namespace": exec_namespace, "name": exec_name, "pod": exec_pod},
            dry_run=dry_run,
        )
        ops_req.params = {
            **(ops_req.params or {}),
            "ai_source": "ai_execute",
            "ai_target": str(target),
            "ai_key": str(sug.key if sug else ""),
            "ai_object_key": str(object_key or ""),
            "ai_action_type": str(action_type or ""),
            "ai_action_kind": str(hint.kind or ""),
            "ai_suggestion_id": str(suggestion_id or ""),
            "ai_expected_kind": str(expected_kind or ""),
        }

        resp = apply_action(ops_req)
        payload = resp.model_dump()
        payload["forbid"] = False
        payload["forbid_reason"] = ""
        payload["cooldown_remaining"] = 0
        payload["limit_remaining"] = 0
        if dry_run:
            payload["planned_action"] = {
                "action_type": action_type,
                "action_kind": str(hint.kind or ""),
                "object_key": object_key,
            }
            payload["evidence_snapshot"] = evidence_snapshot or {}
        return payload

    except (ValueError, IndexError) as e:
        # Re-raise as a standard exception that the worker can catch
        raise Exception(f"invalid parameters: {e}")
    except Exception as e:
        # Log and re-raise the original exception for the worker
        try:
            if "ops_req" in locals():
                log_action(
                    action=str(getattr(ops_req, "action", "") or "UNKNOWN"),
                    target=dict(getattr(ops_req, "target", {}) or {}),
                    params=dict(getattr(ops_req, "params", {}) or {}),
                    dry_run=bool(getattr(ops_req, "dry_run", True)),
                    result="failed",
                    detail=str(e),
                )
        except Exception:
            pass
        try:
            if str(target) == "pod_cpu":
                key = f"{namespace or ''}/{pod or ''}"
            else:
                key = str(node or "")
            _emit_ai_execute_alert(
                target=str(target),
                key=key,
                action_kind=str(expected_kind or ""),
                detail=f"执行建议失败: {e}",
            )
        except Exception:
            pass
        # Re-raise the original exception
        raise e


def _init_task_state(task_id: str, task_type: str = "ai", input_json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = int(time.time())
    create_task(task_id=task_id, type=task_type, input_json=input_json or {})
    return {
        "task_id": task_id,
        "status": "PENDING",
        "created_ts": now,
        "deadline_ts": now + int(TASK_TTL_SEC),
    }


def _update_task_state(task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    status = _ai_to_task_status(str(updates.get("status") or ""))
    result = updates.get("result")
    error = updates.get("error")
    progress = updates.get("progress")
    if status:
        update_task_status(
            task_id=task_id,
            status=status,
            progress=progress if isinstance(progress, (int, float)) else None,
            result=result,
            error=(error.get("detail") if isinstance(error, dict) else error),
        )
    row = get_task_row(task_id)
    if not row:
        return {"task_id": task_id}
    return {
        "task_id": task_id,
        "status": _task_to_ai_status(str(row.get("status") or "")),
        "result": row.get("result"),
        "error": {"detail": row.get("error")} if row.get("error") else None,
        "created_ts": int(row.get("created_at") or 0),
        "deadline_ts": int(row.get("created_at") or 0) + int(TASK_TTL_SEC),
    }


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
    row = get_task_row(task_id)
    if not row:
        return None
    status = _task_to_ai_status(str(row.get("status") or ""))
    created_ts = int(row.get("created_at") or 0)
    deadline_ts = created_ts + int(TASK_TTL_SEC)
    if status in ("PENDING", "RUNNING") and deadline_ts and time.time() > deadline_ts:
        _update_task_state(
            task_id,
            {"status": "FAILED", "error": {"detail": "task timeout"}},
        )
        row = get_task_row(task_id) or row
        status = str(row.get("status") or "")
    return {
        "task_id": task_id,
        "status": status,
        "result": row.get("result"),
        "error": {"detail": row.get("error")} if row.get("error") else None,
        "created_ts": created_ts,
        "deadline_ts": deadline_ts,
    }


def _emit_ai_execute_alert(
    *,
    target: str,
    key: str,
    action_kind: str,
    detail: str,
) -> None:
    labels = {
        "alertname": "AiExecuteFailed",
        "severity": "warning",
        "target": str(target or ""),
        "key": str(key or ""),
        "action_kind": str(action_kind or ""),
    }
    annotations = {
        "summary": f"AI execute failed: {target} {key}",
        "description": str(detail or ""),
    }
    fp = normalize_fingerprint(fingerprint=None, labels=labels)
    upsert_alert(
        fingerprint=fp,
        status="firing",
        labels=labels,
        annotations=annotations,
        starts_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ends_at="",
        source="ai_execute",
    )
    push_alert_async(
        {
            "fingerprint": fp,
            "status": "firing",
            "labels": labels,
            "annotations": annotations,
            "starts_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ends_at": "",
            "source": "ai_execute",
        }
    )


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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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
    payload = {
        "target": target,
        "node": node,
        "namespace": namespace,
        "pod": pod,
        "history_minutes": history_minutes,
        "horizon_minutes": horizon_minutes,
        "minutes": minutes,
        "horizon": horizon,
        "step": step,
        "cache_ttl": cache_ttl,
        "promql": promql,
    }
    if async_mode:
        task_id = uuid.uuid4().hex
        state = _init_task_state(task_id, task_type="ai_forecast", input_json=payload)
        return JSONResponse(content=state)

    try:
        return run_forecast_task(payload)
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
    payload = {
        "target": target,
        "node": node,
        "namespace": namespace,
        "pod": pod,
        "history_minutes": history_minutes,
        "horizon_minutes": horizon_minutes,
        "step": step,
        "threshold": threshold,
        "sustain_minutes": sustain_minutes,
        "use_llm": use_llm,
        "scale_policy": scale_policy,
        "safe_low": safe_low,
        "safe_high": safe_high,
    }
    if async_mode:
        task_id = uuid.uuid4().hex
        state = _init_task_state(task_id, task_type="ai_suggestions", input_json=payload)
        return JSONResponse(content=state)

    try:
        return run_suggestions_task(payload)
    except HTTPException:
        raise
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

    # 其他 kind：返回特定的错误信息而不是抛异常
    unsupported_kinds = {
        "scale_hpa": "自动水平伸缩（HPA）目前不支持，请通过手动配置 HPA 或待系统升级",
        "add_node": "添加节点操作目前不支持，请联系集群管理员手动添加",
        "cordon_node": "隔离节点操作目前不支持，请通过 kubectl cordon 手动执行",
        "investigate_logs": "日志调查操作目前不支持，请通过日志平台查看",
        "enable_rate_limit": "启用限流操作目前不支持，请通过网关配置手动启用",
    }
    error_msg = unsupported_kinds.get(k)
    if error_msg:
        raise HTTPException(
            status_code=501,
            detail=f"不支持的操作类型 '{kind}'：{error_msg}"
        )
    raise HTTPException(
        status_code=400,
        detail=f"未知的操作类型 '{kind}'"
    )


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
    confirm_text: Optional[str] = Query(None, description="required when dry_run=false"),
    exec_namespace: str = Query("default"),
    exec_name: Optional[str] = Query(None, description="deployment name when scaling/restart/tune"),
    exec_pod: Optional[str] = Query(None, description="pod name when restart_pod/delete_pod"),

    # scale_deployment 参数
    exec_replicas: Optional[int] = Query(None, ge=0, description="override final replicas for scale_deployment"),
    exec_replicas_delta: Optional[int] = Query(None, ge=0, description="override replicas_delta for scale_deployment"),

    # 兼容旧参数名称：replicas / cpu_request_m 等
    replicas: Optional[int] = Query(None, ge=0, description="(compat) override final replicas"),
    replicas_delta: Optional[int] = Query(None, ge=0, description="(compat) override replicas_delta"),

    cpu_request_m: Optional[float] = Query(None, ge=0, description="(compat) override cpu_request_m"),
    cpu_limit_m: Optional[float] = Query(None, ge=0, description="(compat) override cpu_limit_m"),
    mem_request_mb: Optional[float] = Query(None, ge=0, description="(compat) override mem_request_mb"),
    mem_limit_mb: Optional[float] = Query(None, ge=0, description="(compat) override mem_limit_mb"),

    # tune_requests_limits 参数
    exec_cpu_request_m: Optional[float] = Query(None, ge=0, description="override cpu_request_m"),
    exec_cpu_limit_m: Optional[float] = Query(None, ge=0, description="override cpu_limit_m"),
    exec_mem_request_mb: Optional[float] = Query(None, ge=0, description="override mem_request_mb"),
    exec_mem_limit_mb: Optional[float] = Query(None, ge=0, description="override mem_limit_mb"),

    # 资源字符串参数（如 "200m"、"256Mi"）
    exec_cpu_request_str: Optional[str] = Query(None, description='override cpu request string, e.g. "200m"'),
    exec_cpu_limit_str: Optional[str] = Query(None, description='override cpu limit string, e.g. "500m"'),
    exec_mem_request_str: Optional[str] = Query(None, description='override mem request string, e.g. "256Mi"'),
    exec_mem_limit_str: Optional[str] = Query(None, description='override mem limit string, e.g. "512Mi"'),
):
    task_id = uuid.uuid4().hex
    input_payload = {
        "target": target,
        "node": node,
        "namespace": namespace,
        "pod": pod,
        "history_minutes": history_minutes,
        "horizon_minutes": horizon_minutes,
        "step": step,
        "threshold": threshold,
        "sustain_minutes": sustain_minutes,
        "scale_policy": scale_policy,
        "safe_low": safe_low,
        "safe_high": safe_high,
        "suggestion_index": suggestion_index,
        "suggestion_id": suggestion_id,
        "expected_kind": expected_kind,
        "dry_run": dry_run,
        "confirm_text": confirm_text,
        "exec_namespace": exec_namespace,
        "exec_name": exec_name,
        "exec_pod": exec_pod,
        "exec_replicas": exec_replicas,
        "exec_replicas_delta": exec_replicas_delta,
        "replicas": replicas,
        "replicas_delta": replicas_delta,
        "cpu_request_m": cpu_request_m,
        "cpu_limit_m": cpu_limit_m,
        "mem_request_mb": mem_request_mb,
        "mem_limit_mb": mem_limit_mb,
        "exec_cpu_request_m": exec_cpu_request_m,
        "exec_cpu_limit_m": exec_cpu_limit_m,
        "exec_mem_request_mb": exec_mem_request_mb,
        "exec_mem_limit_mb": exec_mem_limit_mb,
        "exec_cpu_request_str": exec_cpu_request_str,
        "exec_cpu_limit_str": exec_cpu_limit_str,
        "exec_mem_request_str": exec_mem_request_str,
        "exec_mem_limit_str": exec_mem_limit_str,
    }
    create_task(task_id=task_id, type="ai_execute", input_json=input_payload)
    payload = ApplyActionResp(
        ok=True,
        action="PENDING",
        dry_run=bool(dry_run),
        detail="task submitted",
        data={},
        forbid=False,
        forbid_reason="",
        cooldown_remaining=0,
        limit_remaining=0,
        planned_action=None,
        evidence_snapshot=None,
    ).model_dump()
    payload["task_id"] = task_id
    payload["status"] = "PENDING"
    return JSONResponse(status_code=200, content=payload)


@router.get("/selfcheck")
def ai_selfcheck():
    prom_base, _ = get_value("PROMETHEUS_BASE")
    llm_key, _ = get_value("DEEPSEEK_API_KEY")
    llm_base, _ = get_value("DEEPSEEK_BASE_URL")
    cooldown_minutes = _cfg_int("AI_EXECUTE_COOLDOWN_MINUTES", 10)
    daily_limit = _cfg_int("AI_EXECUTE_DAILY_LIMIT", 20)
    confirm_text = _cfg_str("AI_EXECUTE_CONFIRM_TEXT", "EXECUTE")
    return {
        "prometheus_configured": bool(str(prom_base or "").strip()),
        "llm_configured": bool(str(llm_key or "").strip() and str(llm_base or "").strip()),
        "execute_cooldown_minutes": int(cooldown_minutes),
        "execute_daily_limit": int(daily_limit),
        "confirm_text": str(confirm_text),
        "dev_mode_hint": "?dev=1 or localStorage devMode=true",
    }
