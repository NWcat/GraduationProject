# services/ai/suggest.py
from __future__ import annotations

import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Optional, Dict, Any, Literal, Tuple

from config import settings
from services.ops.runtime_config import get_value
from db.utils.sqlite import get_conn, q
from db.ai.repo import insert_feedback, upsert_evolution, delete_evolution as repo_delete_evolution
from db.ops.heal_state_repo import get_heal_snapshot
from db.ops.actions_repo import get_last_ai_action

from services.ai.cache import ai_cache, build_suggestion_snapshot_key
from services.ai.forecast_cpu import get_cpu_forecast
from services.ai.forecast_mem import get_mem_forecast
from services.ai.forecast_pod_cpu import get_pod_cpu_forecast

from services.ai.anomaly import detect_anomalies
from services.ai.llm_deepseek import DeepSeekClient
from services.ai.schemas import SuggestionsResp, AnomalyResp

from services.ai.rules import RuleContext, run_rules

from services.ops.k8s_api import list_pods
from services.monitoring.prometheus_client import get_pod_cpu_limit_mcpu, prom_query
from typing import List

# ✅ 可选：拿 Deployment 当前副本数（没有也不炸）
try:
    from services.ops.k8s_api import get_deployment_replicas  # type: ignore
except Exception:
    get_deployment_replicas = None  # type: ignore


Target = Literal["node_cpu", "node_mem", "pod_cpu"]
ScalePolicy = Literal["stair", "linear"]
SUGGESTION_SNAPSHOT_TTL_SEC = 300
LLM_SUMMARY_TIMEOUT_SEC = 5


def cache_suggestion_snapshot(suggestions: SuggestionsResp, anomalies_count: int = 0) -> str:
    suggestion_id = uuid.uuid4().hex
    key = build_suggestion_snapshot_key(suggestion_id)
    ai_cache.set(
        key,
        {
            "suggestions": suggestions,
            "anomalies_count": int(anomalies_count),
            "created_ts": int(time.time()),
        },
        ttl=SUGGESTION_SNAPSHOT_TTL_SEC,
    )
    return suggestion_id


def get_suggestion_snapshot(suggestion_id: str) -> Optional[SuggestionsResp]:
    if not suggestion_id:
        return None
    key = build_suggestion_snapshot_key(suggestion_id)
    cached = ai_cache.get(key)
    if not cached:
        return None
    if isinstance(cached, dict) and isinstance(cached.get("suggestions"), SuggestionsResp):
        return cached["suggestions"]
    return None


def get_suggestion_snapshot_details(suggestion_id: str) -> Optional[Tuple[SuggestionsResp, int]]:
    if not suggestion_id:
        return None
    key = build_suggestion_snapshot_key(suggestion_id)
    cached = ai_cache.get(key)
    if not cached:
        return None
    if isinstance(cached, dict) and isinstance(cached.get("suggestions"), SuggestionsResp):
        return cached["suggestions"], int(cached.get("anomalies_count") or 0)
    return None


def _build_llm_messages(sug: SuggestionsResp, anomalies_count: int) -> list[dict]:
    payload = {
        "target": sug.target,
        "key": sug.key,
        "suggestions": [it.model_dump() for it in (sug.suggestions or [])],
        "anomalies_count": int(anomalies_count),
        "meta": sug.meta or {},
    }
    return [
        {
            "role": "system",
            "content": "你是AIOps运维助手。输出：一句结论+关键证据+建议动作（可执行），简洁中文。",
        },
        {"role": "user", "content": f"根据结构化建议生成运维总结：{payload}"},
    ]


def build_llm_summary(sug: SuggestionsResp, anomalies_count: int = 0) -> Optional[str]:
    llm = DeepSeekClient()
    if not llm.enabled():
        return None

    messages = _build_llm_messages(sug, anomalies_count)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.chat, messages, 0.2)
        try:
            return future.result(timeout=LLM_SUMMARY_TIMEOUT_SEC)
        except TimeoutError:
            return None
        except Exception:
            return None


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


def _cfg_bool(k: str, default: bool) -> bool:
    v, _src = get_value(k)
    if v is None:
        return bool(default)
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return bool(default)


def _clamp_ratio(v: float) -> float:
    return max(0.6, min(1.2, float(v)))


def _clamp_sustain(v: int) -> int:
    return max(5, min(60, int(v)))


_PLACEHOLDER_RE = re.compile(r"\?{3,}")


def sanitize_text(text: str, fallback: str) -> str:
    if not text:
        return fallback
    if "<container>" in text or _PLACEHOLDER_RE.search(text):
        return fallback
    return text


def _sanitize_suggestions(sug: SuggestionsResp) -> SuggestionsResp:
    if not sug or not sug.suggestions:
        return sug
    for item in sug.suggestions:
        item.title = sanitize_text(item.title, "已生成运维建议，请结合实际情况处理。")
        item.rationale = sanitize_text(item.rationale, "系统输出中包含占位符，已替换为默认说明。")
    return sug


def _action_type_from_kind(kind: str) -> str:
    k = str(kind or "").lower()
    if k in ("scale_deployment", "scale_hpa", "add_node"):
        return "scale"
    if k in ("tune_requests_limits",):
        return "tune_resources"
    if k in ("restart_deployment", "restart_pod", "delete_pod"):
        return "ops"
    return "alert_only"


def _risk_from_severity(sev: str) -> str:
    s = str(sev or "").lower()
    if s == "critical":
        return "high"
    if s == "warning":
        return "medium"
    return "low"


def _merge_degrade_reason(current: str, reason: str) -> str:
    base = str(current or "").strip()
    extra = str(reason or "").strip()
    if not extra:
        return base
    if not base:
        return extra
    if extra in base.split("|"):
        return base
    return f"{base}|{extra}"


def _anomaly_top(anom: AnomalyResp, limit: int = 5) -> list[dict]:
    points = list(getattr(anom, "anomalies", []) or [])
    out: list[dict] = []
    for p in points[: max(0, int(limit))]:
        out.append(
            {
                "ts": int(getattr(p, "ts", 0) or 0),
                "value": float(getattr(p, "actual", 0.0) or 0.0),
                "score": float(getattr(p, "score", 0.0) or 0.0),
                "reason": str(getattr(p, "reason", "") or ""),
            }
        )
    return out


def _calc_confidence(
    *,
    evidence: Dict[str, Any],
    anomalies_count: int,
    history_points: int,
    forecast_points: int,
    baseline_mape: Optional[float],
    mape: Optional[float],
) -> tuple[float, str]:
    if history_points < 30 or forecast_points <= 0:
        return 0.1, "insufficient_data"

    score = 0.2

    peak = evidence.get("predicted_max_yhat_mcpu") or evidence.get("predicted_max_yhat") or 0.0
    trigger = evidence.get("trigger_threshold_mcpu") or evidence.get("trigger_threshold") or 0.0
    try:
        if float(trigger) > 0:
            ratio = float(peak) / float(trigger)
            score += min(0.3, max(0.0, (ratio - 1.0) * 0.3))
    except Exception:
        pass

    sustain_over = evidence.get("sustain_over_minutes") or 0
    required = evidence.get("required_sustain_minutes") or evidence.get("sustain_minutes") or 0
    try:
        if int(required) > 0:
            sustain_ratio = float(sustain_over) / float(required)
            score += min(0.2, max(0.0, sustain_ratio * 0.2))
    except Exception:
        pass

    if anomalies_count > 0:
        score += min(0.2, float(anomalies_count) * 0.05)

    if history_points >= 120:
        score += 0.1

    degrade_reason = ""
    has_metrics = (mape is not None) or (baseline_mape is not None)
    if not has_metrics:
        degrade_reason = "no_metrics"
        score *= 0.7
    try:
        low_fit = False
        if baseline_mape is not None and float(baseline_mape) > 0.5:
            low_fit = True
        if mape is not None and float(mape) > 0.4:
            low_fit = True
        if low_fit:
            score *= 0.7
            degrade_reason = _merge_degrade_reason(degrade_reason, "low_model_fit")
    except Exception:
        pass

    score = max(0.05, min(1.0, score))
    return score, degrade_reason


def _count_feedback(target: str, key: str) -> int:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT COUNT(1) AS c FROM ai_feedback WHERE target=? AND key=?", (target, key))
        row = cur.fetchone()
        return int(row["c"]) if row else 0
    finally:
        conn.close()


def _get_evolution_row(target: str, key: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = q(
            conn,
            "SELECT target, key, observe_ratio, trigger_ratio, sustain_minutes, updated_ts FROM ai_evolution WHERE target=? AND key=?",
            (target, key),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "target": str(row["target"]),
            "key": str(row["key"]),
            "observe_ratio": float(row["observe_ratio"]),
            "trigger_ratio": float(row["trigger_ratio"]),
            "sustain_minutes": int(row["sustain_minutes"]),
            "updated_ts": int(row["updated_ts"]),
        }
    finally:
        conn.close()


def _parse_detail_level(detail: str) -> Optional[str]:
    if not detail:
        return None
    d = detail.strip()
    if not d:
        return None
    if d.startswith("{") and d.endswith("}"):
        try:
            payload = json.loads(d)
            for k in ("class", "level", "type"):
                v = payload.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip().lower()
        except Exception:
            return None
    lowered = d.lower()
    if "near" in lowered or "接近" in lowered:
        return "near"
    if "trigger" in lowered or "超阈值" in lowered or "高风险" in lowered:
        return "strong"
    return None


def _classify_feedback(
    target: str,
    outcome: str,
    action_kind: str,
    detail: str,
    suggestion_id: str,
) -> Optional[str]:
    if target != "pod_cpu":
        return None
    level = _parse_detail_level(detail)
    if level == "near":
        return "near"
    if level == "strong":
        return "strong"

    if suggestion_id:
        cached = get_suggestion_snapshot(suggestion_id)
        if cached and cached.suggestions:
            for item in cached.suggestions:
                evidence = item.evidence or {}
                rule_name = str(evidence.get("rule_name") or "")
                status = str(evidence.get("status") or "")
                if rule_name == "pod_cpu_base" and status == "near":
                    return "near"
                if rule_name == "pod_cpu_triggered":
                    return "strong"

    k = (action_kind or "").lower()
    if k in ("scale_deployment", "enable_rate_limit"):
        return "strong"
    return None


def get_effective_evolution_params(
    target: str,
    key: str,
    *,
    observe_ratio: float,
    trigger_ratio: float,
    critical_ratio: float,
    sustain_minutes: int,
    enabled: bool,
) -> Tuple[Dict[str, Any], str]:
    if not enabled:
        return (
            {
                "observe_ratio": float(observe_ratio),
                "trigger_ratio": float(trigger_ratio),
                "critical_ratio": float(critical_ratio),
                "sustain_minutes": int(sustain_minutes),
            },
            "default",
        )
    row = _get_evolution_row(target, key)
    if not row:
        return (
            {
                "observe_ratio": float(observe_ratio),
                "trigger_ratio": float(trigger_ratio),
                "critical_ratio": float(critical_ratio),
                "sustain_minutes": int(sustain_minutes),
            },
            "default",
        )
    return (
        {
            "observe_ratio": float(row["observe_ratio"]),
            "trigger_ratio": float(row["trigger_ratio"]),
            "critical_ratio": float(critical_ratio),
            "sustain_minutes": int(row["sustain_minutes"]),
        },
        "db",
    )


def apply_feedback_evolution(
    *,
    target: str,
    key: str,
    action_kind: str,
    outcome: str,
    detail: str,
    suggestion_id: str,
) -> Optional[Dict[str, Any]]:
    enabled = _cfg_bool("AI_EVOLUTION_ENABLED", False)
    if not enabled or target != "pod_cpu":
        return None

    min_feedbacks = _cfg_int("AI_EVOLUTION_MIN_FEEDBACKS", 3)
    max_delta = _cfg_float("AI_EVOLUTION_MAX_DELTA", 0.05)
    if max_delta <= 0:
        return None

    feedback_count = _count_feedback(target, key)
    if feedback_count < min_feedbacks:
        return None

    level = _classify_feedback(target, outcome, action_kind, detail, suggestion_id)
    if not level:
        return None

    default_observe = _cfg_float(
        "AUTO_POD_CPU_THRESHOLD_RATIO",
        float(getattr(settings, "AUTO_POD_CPU_THRESHOLD_RATIO", 0.80)),
    )
    default_trigger = _cfg_float(
        "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO",
        float(getattr(settings, "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO", 0.90)),
    )
    default_sustain = _cfg_int(
        "AUTO_POD_CPU_SUSTAIN_MINUTES",
        int(getattr(settings, "AUTO_POD_CPU_SUSTAIN_MINUTES", 10)),
    )

    current, _src = get_effective_evolution_params(
        target,
        key,
        observe_ratio=default_observe,
        trigger_ratio=default_trigger,
        critical_ratio=1.0,
        sustain_minutes=default_sustain,
        enabled=True,
    )
    observe_ratio = float(current["observe_ratio"])
    trigger_ratio = float(current["trigger_ratio"])
    sustain_minutes = int(current["sustain_minutes"])

    delta_ratio = min(float(max_delta), 0.05)
    updated = False

    if outcome == "ignored" and level == "near":
        observe_ratio = _clamp_ratio(observe_ratio + delta_ratio)
        if trigger_ratio < observe_ratio:
            trigger_ratio = observe_ratio
        updated = True

    if outcome == "fail" and level == "strong":
        delta_minutes = max(1, int(round(sustain_minutes * delta_ratio)))
        if sustain_minutes < 60:
            sustain_minutes = _clamp_sustain(sustain_minutes + delta_minutes)
            updated = True
        elif trigger_ratio > 0.6:
            trigger_ratio = _clamp_ratio(trigger_ratio - delta_ratio)
            if observe_ratio > trigger_ratio:
                observe_ratio = trigger_ratio
            updated = True

    if not updated:
        return None

    upsert_evolution(
        target=target,
        key=key,
        observe_ratio=observe_ratio,
        trigger_ratio=trigger_ratio,
        sustain_minutes=sustain_minutes,
    )
    return {
        "target": target,
        "key": key,
        "observe_ratio": observe_ratio,
        "trigger_ratio": trigger_ratio,
        "critical_ratio": 1.0,
        "sustain_minutes": sustain_minutes,
    }


def record_feedback(
    *,
    target: str,
    key: str,
    action_kind: str,
    outcome: str,
    detail: Optional[str],
    suggestion_id: Optional[str],
    ts: Optional[int],
) -> Dict[str, Any]:
    now_ts = int(ts or time.time())
    feedback_id = insert_feedback(
        ts=now_ts,
        target=target,
        key=key,
        suggestion_id=suggestion_id or "",
        action_kind=action_kind,
        outcome=outcome,
        detail=detail or "",
    )
    evolution = apply_feedback_evolution(
        target=target,
        key=key,
        action_kind=action_kind,
        outcome=outcome,
        detail=detail or "",
        suggestion_id=suggestion_id or "",
    )
    return {"feedback_id": feedback_id, "evolution": evolution}


def get_evolution_view(target: str, key: str) -> Tuple[Dict[str, Any], str, bool]:
    default_observe = _cfg_float(
        "AUTO_POD_CPU_THRESHOLD_RATIO",
        float(getattr(settings, "AUTO_POD_CPU_THRESHOLD_RATIO", 0.80)),
    )
    default_trigger = _cfg_float(
        "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO",
        float(getattr(settings, "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO", 0.90)),
    )
    default_sustain = _cfg_int(
        "AUTO_POD_CPU_SUSTAIN_MINUTES",
        int(getattr(settings, "AUTO_POD_CPU_SUSTAIN_MINUTES", 10)),
    )
    critical_ratio = 1.0
    enabled = _cfg_bool("AI_EVOLUTION_ENABLED", False)
    row = _get_evolution_row(target, key)
    if row:
        return (
            {
                "observe_ratio": float(row["observe_ratio"]),
                "trigger_ratio": float(row["trigger_ratio"]),
                "critical_ratio": float(critical_ratio),
                "sustain_minutes": int(row["sustain_minutes"]),
            },
            "db",
            enabled,
        )
    return (
        {
            "observe_ratio": float(default_observe),
            "trigger_ratio": float(default_trigger),
            "critical_ratio": float(critical_ratio),
            "sustain_minutes": int(default_sustain),
        },
        "default",
        enabled,
    )


def delete_evolution(target: str, key: str) -> bool:
    return repo_delete_evolution(target=target, key=key)


def _enrich_pod_meta(namespace: str, pod: str) -> Dict[str, Any]:
    """
    给 pod_cpu 的 forecast.meta 补齐：
    - limit_mcpu（主路径）
    - controller_kind / deployment_name / deployment_uid
    - current_replicas（可选：用于 linear 策略）
    """
    meta: Dict[str, Any] = {}

    limit = get_pod_cpu_limit_mcpu(namespace=namespace, pod=pod)
    if limit is not None:
        meta["limit_mcpu"] = float(limit)
    meta["has_limit"] = bool(limit is not None and float(limit) > 0)

    # pod -> deployment 映射（只对 ReplicaSet 的 Deployment 走联动）
    pods = list_pods(namespace=namespace)
    for p in pods:
        if p.get("namespace") == namespace and p.get("name") == pod:
            meta["controller_kind"] = p.get("controller_kind")
            meta["controller_name"] = p.get("controller_name")
            meta["deployment_name"] = p.get("deployment_name") or "unknown"
            meta["deployment_uid"] = p.get("deployment_uid") or "unknown"
            controller_kind = str(meta.get("controller_kind") or "")
            controller_name = str(meta.get("controller_name") or "")
            if controller_kind == "ReplicaSet":
                dep = str(meta.get("deployment_name") or "unknown")
                if dep != "unknown":
                    meta["workload_kind"] = "Deployment"
                    meta["workload_name"] = dep
                else:
                    meta["workload_kind"] = "ReplicaSet"
                    meta["workload_name"] = controller_name or "unknown"
            elif controller_kind in ("Deployment", "StatefulSet", "DaemonSet"):
                meta["workload_kind"] = controller_kind
                meta["workload_name"] = controller_name or "unknown"
            else:
                meta["workload_kind"] = "Unknown"
                meta["workload_name"] = "unknown"
            break

    # ✅ 补 peer pods CPU usages（给 rules.py 的热点识别用）
    if (
        meta.get("controller_kind") == "ReplicaSet"
        and (meta.get("deployment_name") or "unknown") != "unknown"
    ):
        try:
            peers = _get_deployment_peer_pods_cpu_mcpu(namespace, str(meta["deployment_name"]))
            if peers:
                # 让 rules.py 的 _extract_pod_cpu_usages_mcpu 能拿到
                meta["peer_pods_cpu_mcpu"] = peers
                # 也可以同时放一个更直观的名字
                meta["deployment_pod_usages_mcpu"] = peers
        except Exception:
            pass

    # ✅ 补 current_replicas（linear 必需；拿不到就不写，rules.py 会自动退化 stair）
    if (
        meta.get("controller_kind") == "ReplicaSet"
        and (meta.get("deployment_name") or "unknown") != "unknown"
        and callable(get_deployment_replicas)
    ):
        try:
            cr = get_deployment_replicas(namespace=namespace, name=str(meta["deployment_name"]))
            meta["current_replicas"] = int(cr)
        except Exception:
            pass

    return meta


def _detect_base_limit_source(forecast: Any) -> str:
    meta = getattr(forecast, "meta", None) or {}
    limit_mcpu = None
    try:
        limit_mcpu = float(meta.get("limit_mcpu", 0.0))
    except Exception:
        limit_mcpu = 0.0
    has_limit = bool(meta.get("has_limit")) if "has_limit" in meta else limit_mcpu > 0
    if has_limit and limit_mcpu > 0:
        return "limit"
    history = getattr(forecast, "history", None) or []
    for p in history:
        v = p.get("value") if isinstance(p, dict) else getattr(p, "value", 0.0)
        if v is not None and float(v) >= 0:
            return "derived"
    return "none"


def build_suggestions(
    target: Target,
    node: Optional[str] = None,
    namespace: Optional[str] = None,
    pod: Optional[str] = None,
    history_minutes: int = 240,
    horizon_minutes: int = 120,
    step: int = 60,
    threshold: float = 85.0,
    sustain_minutes: int = 15,
    use_llm: bool = True,
    # ✅ 新增：扩容策略选择透传（配合你新版 rules.py）
    scale_policy: ScalePolicy = "stair",
    safe_low: float = 0.6,
    safe_high: float = 0.7,
) -> Dict[str, Any]:
    if target == "node_cpu":
        if not node:
            raise ValueError("node required for node_cpu")
        fc = get_cpu_forecast(node=node, minutes=history_minutes, horizon=horizon_minutes, step=step, cache_ttl=30)
        ctx = RuleContext(
            target="node_cpu",
            key=node,
            node=node,
            forecast=fc,
            threshold=threshold,
            sustain_minutes=sustain_minutes,
        )
        meta = fc.meta or {}
        if isinstance(meta, dict):
            meta = dict(meta)
            meta["baseline_mape"] = float(getattr(fc.metrics, "baseline_mape", 0.0))
        sug = SuggestionsResp(target="node_cpu", key=node, suggestions=run_rules(ctx), meta=meta)
        anom: AnomalyResp = detect_anomalies("node_cpu", node, fc.history, fc.forecast, history_minutes, step)

    elif target == "node_mem":
        if not node:
            raise ValueError("node required for node_mem")
        fc = get_mem_forecast(node=node, minutes=history_minutes, horizon=horizon_minutes, step=step, cache_ttl=30)
        ctx = RuleContext(
            target="node_mem",
            key=node,
            node=node,
            forecast=fc,
            threshold=threshold,
            sustain_minutes=sustain_minutes,
        )
        meta = fc.meta or {}
        if isinstance(meta, dict):
            meta = dict(meta)
            meta["baseline_mape"] = float(getattr(fc.metrics, "baseline_mape", 0.0))
        sug = SuggestionsResp(target="node_mem", key=node, suggestions=run_rules(ctx), meta=meta)
        anom = detect_anomalies("node_mem", node, fc.history, fc.forecast, history_minutes, step)

    else:  # pod_cpu
        if not (namespace and pod):
            raise ValueError("namespace/pod required for pod_cpu")

        fc = get_pod_cpu_forecast(
            namespace=namespace, pod=pod, minutes=history_minutes, horizon=horizon_minutes, step=step, cache_ttl=30
        )

        # ✅ 阶段2：补齐 limit + deployment 映射 + current_replicas（可选）
        extra = _enrich_pod_meta(namespace=namespace, pod=pod)
        fc.meta = {**(fc.meta or {}), **extra}

        key = f"{namespace}/{pod}"

        # ✅ 运行时读取（DB override 立即生效）> settings/.env > default
        observe_ratio = _cfg_float(
            "AUTO_POD_CPU_THRESHOLD_RATIO",
            float(getattr(settings, "AUTO_POD_CPU_THRESHOLD_RATIO", 0.80)),
        )
        trigger_ratio = _cfg_float(
            "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO",
            float(getattr(settings, "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO", 0.90)),
        )
        sustain_m = _cfg_int(
            "AUTO_POD_CPU_SUSTAIN_MINUTES",
            int(getattr(settings, "AUTO_POD_CPU_SUSTAIN_MINUTES", 10)),
        )
        critical_ratio = 1.0
        evolution_enabled = _cfg_bool("AI_EVOLUTION_ENABLED", False)
        evo_params, evo_src = get_effective_evolution_params(
            "pod_cpu",
            key,
            observe_ratio=observe_ratio,
            trigger_ratio=trigger_ratio,
            critical_ratio=critical_ratio,
            sustain_minutes=sustain_m,
            enabled=evolution_enabled,
        )
        observe_ratio = _clamp_ratio(evo_params["observe_ratio"])
        trigger_ratio = _clamp_ratio(evo_params["trigger_ratio"])
        sustain_m = _clamp_sustain(evo_params["sustain_minutes"])
        if trigger_ratio < observe_ratio:
            trigger_ratio = observe_ratio
        if critical_ratio < trigger_ratio:
            critical_ratio = trigger_ratio

        # ✅ 透传策略选择：stair / linear + safe_low/high
        ctx = RuleContext(
            target="pod_cpu",
            key=key,
            namespace=namespace,
            pod=pod,
            forecast=fc,
            threshold_ratio=observe_ratio,
            high_threshold_ratio=trigger_ratio,
            observe_ratio=observe_ratio,
            trigger_ratio=trigger_ratio,
            critical_ratio=critical_ratio,
            sustain_minutes=sustain_m,
            scale_policy=scale_policy,
            safe_low=safe_low,
            safe_high=safe_high,
        )
        meta = fc.meta or {}
        if isinstance(meta, dict):
            meta = dict(meta)
            meta["baseline_mape"] = float(getattr(fc.metrics, "baseline_mape", 0.0))
        sug = SuggestionsResp(target="pod_cpu", key=key, suggestions=run_rules(ctx), meta=meta)
        base_limit_source = _detect_base_limit_source(fc)
        meta = sug.meta or {}
        if isinstance(meta, dict):
            meta = dict(meta)
            meta["params_used"] = {
                "observe_ratio": round(observe_ratio, 3),
                "trigger_ratio": round(trigger_ratio, 3),
                "sustain_minutes": int(sustain_m),
                "base_limit_source": base_limit_source,
            }
            meta["evolution_source"] = evo_src
        sug.meta = meta

        anom = detect_anomalies("pod_cpu", key, fc.history, fc.forecast, history_minutes, step)

    sug = _sanitize_suggestions(sug)

    # apply AI fields: evidence/confidence/risk/degrade_reason/action_type
    anomalies_count = len(getattr(anom, "anomalies", []) or [])
    anomalies_top = _anomaly_top(anom, limit=5)
    history_points = len(getattr(fc, "history", []) or []) if "fc" in locals() else 0
    forecast_points = len(getattr(fc, "forecast", []) or []) if "fc" in locals() else 0
    metrics = getattr(fc, "metrics", None) if "fc" in locals() else None
    baseline_mape = float(getattr(metrics, "baseline_mape", 0.0)) if metrics is not None else None
    mape = float(getattr(metrics, "mape", 0.0)) if metrics is not None else None

    cooldown_minutes = _cfg_int("AI_EXECUTE_COOLDOWN_MINUTES", 10)
    daily_limit = _cfg_int("AI_EXECUTE_DAILY_LIMIT", 20)

    heal_snapshot = None
    object_key = None
    if target == "pod_cpu":
        meta = sug.meta or {}
        if isinstance(meta, dict):
            ns = str(namespace or "default")
            duid = str(meta.get("deployment_uid") or "")
            object_key = f"{ns}/{duid}" if duid else key
            if duid:
                heal_snapshot = get_heal_snapshot(namespace=ns, deployment_uid=duid)
    else:
        object_key = str(sug.key or "")

    for item in (sug.suggestions or []):
        evidence = item.evidence or {}
        if isinstance(evidence, dict):
            evidence = dict(evidence)
            evidence.setdefault("history_points", int(history_points))
            evidence.setdefault("forecast_points", int(forecast_points))
            evidence.setdefault("anomalies_count", int(anomalies_count))
            evidence.setdefault("anomalies", {"count": int(anomalies_count), "top": anomalies_top})
            evidence.setdefault("execute_guard", {"cooldown_minutes": int(cooldown_minutes), "daily_limit": int(daily_limit)})
            if object_key:
                evidence.setdefault("object_key", object_key)
            if heal_snapshot:
                evidence.setdefault("heal", dict(heal_snapshot))
            item.evidence = evidence
        item.action_type = _action_type_from_kind(getattr(item.action, "kind", ""))
        conf, degrade_reason = _calc_confidence(
            evidence=item.evidence or {},
            anomalies_count=anomalies_count,
            history_points=history_points,
            forecast_points=forecast_points,
            baseline_mape=baseline_mape,
            mape=mape,
        )
        if degrade_reason:
            item.degrade_reason = _merge_degrade_reason(item.degrade_reason, degrade_reason)
        if history_points < 30 or forecast_points <= 0:
            item.action_type = "alert_only"
            item.degrade_reason = _merge_degrade_reason(item.degrade_reason, "insufficient_data")
            item.confidence = 0.1
        else:
            item.confidence = float(conf)

        if heal_snapshot:
            status = str(heal_snapshot.get("status") or "")
            if status == "circuit_open":
                item.confidence = max(0.05, item.confidence * 0.5)
                item.degrade_reason = _merge_degrade_reason(item.degrade_reason, "circuit_breaker")
                item.action_type = "alert_only"
            elif status == "pending":
                item.confidence = max(0.05, item.confidence * 0.7)
                item.degrade_reason = _merge_degrade_reason(item.degrade_reason, "pending_heal")

        if item.action_type not in ("scale", "tune_resources", "ops", "alert_only"):
            item.action_type = "alert_only"

        item.risk = _risk_from_severity(str(item.severity or ""))

        if item.action_type and object_key:
            last_action = get_last_ai_action(object_key=object_key, action_type=item.action_type)
            if last_action:
                exec_info = {
                    "ts": int(last_action.get("ts") or 0),
                    "result": str(last_action.get("result") or ""),
                    "detail": str(last_action.get("detail") or ""),
                    "action": str(last_action.get("action") or ""),
                    "dry_run": bool(last_action.get("dry_run") or 0),
                }
                evidence = item.evidence or {}
                if isinstance(evidence, dict):
                    evidence["execute"] = exec_info
                    evidence["last_execute_failed"] = exec_info.get("result") == "failed"
                    if exec_info.get("result") == "failed":
                        evidence["fail_reason"] = exec_info.get("detail") or ""
                item.evidence = evidence

    llm_summary: Optional[str] = None
    if use_llm:
        llm_summary = build_llm_summary(sug, anomalies_count=len(getattr(anom, "anomalies", []) or []))

    if llm_summary:
        sug.llm_summary = llm_summary

    return {"suggestions": sug, "anomalies": anom, "llm_summary": llm_summary}

def _get_deployment_peer_pods_cpu_mcpu(namespace: str, deployment_name: str) -> List[float]:
    """
    拉取同一个 Deployment 下各 Pod 的 CPU 使用（mCPU）。
    PromQL：sum(rate(container_cpu_usage_seconds_total{...}[5m])) by (pod) * 1000
    """
    if not prom_query or not deployment_name:
        return []

    # Pod 名通常是 <deployment>-<hash>-<suffix>
    pod_re = re.escape(deployment_name) + r"-.*"

    q = (
        f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",pod=~"{pod_re}",container!="POD"}}[5m])) by (pod) * 1000'
    )
    try:
        data = prom_query(q)
        # 兼容 Prometheus vector 返回结构
        results = (((data or {}).get("data") or {}).get("result")) or []
        out: List[float] = []
        for r in results:
            v = (r.get("value") or [None, "0"])[1]
            out.append(float(v))
        return [x for x in out if x >= 0.0]
    except Exception:
        return []
