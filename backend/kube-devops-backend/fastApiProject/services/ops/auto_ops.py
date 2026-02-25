# services/ops/auto_ops.py
from __future__ import annotations

from typing import Dict, Any, Optional
import time

from config import settings
from db.utils.sqlite import get_conn, q
from services.ai.suggest import build_suggestions
from services.ops.actions import apply_action
from services.ops.schemas import ApplyActionReq
from services.alerts.client import push_alert

from services.ops.runtime_config import get_value  # ✅ DB override > env/settings > default


def _cfg_bool(k: str, default: bool) -> bool:
    v, _src = get_value(k)
    try:
        return bool(v)
    except Exception:
        return bool(default)


def _cfg_int(k: str, default: int) -> int:
    v, _src = get_value(k)
    try:
        return int(v)
    except Exception:
        return int(default)


def _cfg_float(k: str, default: float) -> float:
    v, _src = get_value(k)
    try:
        return float(v)
    except Exception:
        return float(default)


def _get_last_ts(key: str) -> Optional[int]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT ts FROM ops_cooldown WHERE k=?", (key,))
        row = cur.fetchone()
        if not row:
            return None
        return int(row["ts"])
    finally:
        conn.close()


def _set_last_ts(key: str, ts: int) -> None:
    conn = get_conn()
    try:
        q(conn, "INSERT OR REPLACE INTO ops_cooldown(k, ts) VALUES(?,?)", (key, int(ts)))
        conn.commit()
    finally:
        conn.close()


def _ck(ns: str, duid: str) -> str:
    return f"autoscale:{ns}/{duid}"


def run_pre_scale_once_for_pod_cpu(
    *,
    namespace: str,
    pod: str,
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    ✅ 阶段2：pod_cpu 预测 -> deployment 预扩容联动
    - 主路径：predicted_peak/limit >= threshold
    - 无 limit：只告警，不扩容
    - cooldown：同 deployment_uid 在 cooldown 内不重复扩容

    配置优先级：DB override（前端） > settings/.env > default
    """
    # ✅ 运行时读取，确保 DB override 立即生效
    auto_enabled = _cfg_bool("AUTO_OPS_ENABLED", bool(getattr(settings, "AUTO_OPS_ENABLED", False)))
    auto_execute = _cfg_bool("AUTO_OPS_EXECUTE", bool(getattr(settings, "AUTO_OPS_EXECUTE", False)))

    auto_cooldown_sec = _cfg_int("AUTO_OPS_COOLDOWN_SEC", int(getattr(settings, "AUTO_OPS_COOLDOWN_SEC", 300)))
    threshold_ratio = _cfg_float("AUTO_POD_CPU_THRESHOLD_RATIO", float(getattr(settings, "AUTO_POD_CPU_THRESHOLD_RATIO", 0.80)))
    high_threshold_ratio = _cfg_float("AUTO_POD_CPU_HIGH_THRESHOLD_RATIO", float(getattr(settings, "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO", 0.90)))
    sustain_minutes = _cfg_int("AUTO_POD_CPU_SUSTAIN_MINUTES", int(getattr(settings, "AUTO_POD_CPU_SUSTAIN_MINUTES", 10)))

    if not auto_enabled:
        return {"ok": False, "reason": "AUTO_OPS_ENABLED=0"}

    ns = (namespace or "default").strip() or "default"
    p = (pod or "").strip()
    if not p:
        return {"ok": False, "reason": "pod required"}

    dry = (not auto_execute) if dry_run is None else bool(dry_run)

    out = build_suggestions(
        target="pod_cpu",
        namespace=ns,
        pod=p,
        history_minutes=240,
        horizon_minutes=120,
        step=60,
        use_llm=False,
    )

    sug = out["suggestions"]
    items = list(getattr(sug, "suggestions", []) or [])

    # 找 scale_deployment 建议
    scale_item = None
    for it in items:
        act = getattr(it, "action", None)
        if act and getattr(act, "kind", "") == "scale_deployment":
            scale_item = it
            break

    meta = sug.meta or {}
    if not scale_item:
        # 没有可执行动作：如果是 alert_only，也发个“预测过载/缺limit/不持续”的告警（可审计）
        reason = "no_scale_action"
        if items:
            a0 = getattr(items[0], "action", None)
            if a0 and getattr(a0, "kind", "") == "alert_only":
                reason = (getattr(a0, "params", {}) or {}).get("reason", "alert_only")

        alert = push_alert(
            alertname="PredictOverload",
            severity="warning",
            labels={
                "namespace": ns,
                "pod": p,
                "reason": str(reason),
                "deployment_name": str(meta.get("deployment_name") or "unknown"),
                "deployment_uid": str(meta.get("deployment_uid") or "unknown"),
            },
            annotations={
                "summary": f"[Predict] {ns}/{p} overload signal ({reason})",
                "description": f"pod_cpu prediction produced no scale action. reason={reason}, meta={meta}",
            },
        )
        return {"ok": True, "triggered": False, "reason": reason, "meta": meta, "alert": alert}

    params = (scale_item.action.params or {})  # type: ignore
    dname = str(params.get("deployment_name") or meta.get("deployment_name") or "unknown")
    duid = str(params.get("deployment_uid") or meta.get("deployment_uid") or "unknown")
    delta = int(params.get("replicas_delta") or 1)

    peak = float(params.get("peak_pred_mcpu") or 0.0)
    limit_mcpu = params.get("limit_mcpu")
    ratio = float(params.get("ratio") or 0.0)

    # 没有 deployment_uid 不能做 cooldown
    if duid == "unknown" or dname == "unknown":
        alert = push_alert(
            alertname="PredictOverload",
            severity="warning",
            labels={
                "namespace": ns,
                "pod": p,
                "deployment_name": dname,
                "deployment_uid": duid,
                "reason": "missing_deployment_mapping",
            },
            annotations={
                "summary": f"[Predict] {ns}/{p} overload but cannot map to deployment",
                "description": f"cannot auto scale: deployment_name/deployment_uid missing. meta={meta}",
            },
        )
        return {"ok": True, "triggered": False, "reason": "missing_deployment_mapping", "meta": meta, "alert": alert}

    # cooldown
    now_ts = int(time.time())
    ck = _ck(ns, duid)
    last_ts = _get_last_ts(ck)
    if last_ts is not None and (now_ts - int(last_ts)) < auto_cooldown_sec:
        alert = push_alert(
            alertname="PredictOverload",
            severity="info",
            labels={
                "namespace": ns,
                "pod": p,
                "deployment_name": dname,
                "deployment_uid": duid,
                "cooldown": "1",
            },
            annotations={
                "summary": f"[Predict] cooldown active for {ns}/{dname}",
                "description": f"skip autoscale due to cooldown ({now_ts - int(last_ts)}s/{auto_cooldown_sec}s). "
                               f"peak={peak}m, limit={limit_mcpu}, ratio={ratio}, delta={delta}, dry_run={dry}",
            },
        )
        return {"ok": True, "triggered": False, "cooldown": True, "last_ts": int(last_ts), "alert": alert}

    # 先发预测过载告警（每次触发扩容都会发）
    predict_alert = push_alert(
        alertname="PredictOverload",
        severity="warning",
        labels={
            "namespace": ns,
            "pod": p,
            "deployment_name": dname,
            "deployment_uid": duid,
            "threshold_ratio": str(threshold_ratio),
            "high_threshold_ratio": str(high_threshold_ratio),
        },
        annotations={
            "summary": f"[Predict] overload risk for {ns}/{dname}",
            "description": f"peak={peak:.0f}mCPU, limit={float(limit_mcpu) if limit_mcpu else 'None'}mCPU, "
                           f"ratio={ratio:.3f}, suggest_delta={delta}, sustain={sustain_minutes}m",
        },
    )

    # 执行动作：SCALE_DEPLOYMENT（只对 Deployment）
    req = ApplyActionReq(
        action="SCALE_DEPLOYMENT",
        target={"namespace": ns, "name": dname},
        params={
            "replicas_delta": delta,
            "reason": "predict_overload",
            "pod": p,
            "deployment_uid": duid,
            "peak_pred_mcpu": peak,
            "limit_mcpu": float(limit_mcpu) if limit_mcpu else None,
            "ratio": ratio,
            "threshold_ratio": threshold_ratio,
            "high_threshold_ratio": high_threshold_ratio,
            "sustain_minutes": sustain_minutes,
        },
        dry_run=dry,
    )
    resp = apply_action(req)

    # 扩容后告警（包含 before/after + dry_run）
    data = resp.data or {}
    scale_alert = push_alert(
        alertname="AutoScaleDeployment",
        severity="warning" if (not dry) else "info",
        labels={
            "namespace": ns,
            "deployment_name": dname,
            "deployment_uid": duid,
            "dry_run": "1" if dry else "0",
        },
        annotations={
            "summary": f"[AutoScale] {ns}/{dname} {'dry-run' if dry else 'scaled'}",
            "description": f"before={data.get('before_replicas')} after={data.get('after_replicas')} "
                           f"delta={delta} ratio={ratio:.3f} peak={peak:.0f}m",
        },
    )

    # 真执行才写 cooldown
    if resp.ok and (not dry):
        _set_last_ts(ck, now_ts)

    return {
        "ok": True,
        "triggered": True,
        "dry_run": dry,
        "deployment_name": dname,
        "deployment_uid": duid,
        "replicas_delta": delta,
        "predict_alert": predict_alert,
        "action": resp.model_dump(),
        "scale_alert": scale_alert,
    }
