# services/ai/suggest.py
from __future__ import annotations

import re
from typing import Optional, Dict, Any, Literal

from config import settings
from services.ops.runtime_config import get_value

from services.ai.forecast_cpu import get_cpu_forecast
from services.ai.forecast_mem import get_mem_forecast
from services.ai.forecast_pod_cpu import get_pod_cpu_forecast

from services.ai.anomaly import detect_anomalies
from services.ai.llm_deepseek import DeepSeekClient
from services.ai.schemas import SuggestionsResp, AnomalyResp

from services.ai.rules import (
    generate_node_cpu_suggestions,
    generate_node_mem_suggestions,
    generate_pod_cpu_suggestions,
)

from services.ops.k8s_api import list_pods
from services.prometheus_client import get_pod_cpu_limit_mcpu, prom_query
from typing import List

# ✅ 可选：拿 Deployment 当前副本数（没有也不炸）
try:
    from services.ops.k8s_api import get_deployment_replicas  # type: ignore
except Exception:
    get_deployment_replicas = None  # type: ignore


Target = Literal["node_cpu", "node_mem", "pod_cpu"]
ScalePolicy = Literal["stair", "linear"]


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

    # pod -> deployment 映射（只对 ReplicaSet 的 Deployment 走联动）
    pods = list_pods(namespace=namespace)
    for p in pods:
        if p.get("namespace") == namespace and p.get("name") == pod:
            meta["controller_kind"] = p.get("controller_kind")
            meta["deployment_name"] = p.get("deployment_name") or "unknown"
            meta["deployment_uid"] = p.get("deployment_uid") or "unknown"
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
    llm = DeepSeekClient()

    if target == "node_cpu":
        if not node:
            raise ValueError("node required for node_cpu")
        fc = get_cpu_forecast(node=node, minutes=history_minutes, horizon=horizon_minutes, step=step, cache_ttl=30)
        sug: SuggestionsResp = generate_node_cpu_suggestions(
            node=node, forecast=fc, threshold=threshold, sustain_minutes=sustain_minutes
        )
        anom: AnomalyResp = detect_anomalies("node_cpu", node, fc.history, fc.forecast, history_minutes, step)

    elif target == "node_mem":
        if not node:
            raise ValueError("node required for node_mem")
        fc = get_mem_forecast(node=node, minutes=history_minutes, horizon=horizon_minutes, step=step, cache_ttl=30)
        sug = generate_node_mem_suggestions(node=node, forecast=fc, threshold=threshold, sustain_minutes=sustain_minutes)
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
        threshold_ratio = _cfg_float(
            "AUTO_POD_CPU_THRESHOLD_RATIO",
            float(getattr(settings, "AUTO_POD_CPU_THRESHOLD_RATIO", 0.80)),
        )
        high_threshold_ratio = _cfg_float(
            "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO",
            float(getattr(settings, "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO", 0.90)),
        )
        sustain_m = _cfg_int(
            "AUTO_POD_CPU_SUSTAIN_MINUTES",
            int(getattr(settings, "AUTO_POD_CPU_SUSTAIN_MINUTES", 10)),
        )

        # ✅ 透传策略选择：stair / linear + safe_low/high
        sug = generate_pod_cpu_suggestions(
            namespace=namespace,
            pod=pod,
            forecast=fc,
            threshold_ratio=threshold_ratio,
            high_threshold_ratio=high_threshold_ratio,
            sustain_minutes=sustain_m,
            scale_policy=scale_policy,
            safe_low=safe_low,
            safe_high=safe_high,
        )

        anom = detect_anomalies("pod_cpu", key, fc.history, fc.forecast, history_minutes, step)

    llm_summary: Optional[str] = None
    if use_llm and llm.enabled():
        payload = {
            "target": sug.target,
            "key": sug.key,
            "suggestions": [it.model_dump() for it in (sug.suggestions or [])],
            "anomalies_count": len(getattr(anom, "anomalies", []) or []),
            "meta": sug.meta or {},
        }
        messages = [
            {"role": "system", "content": "你是AIOps运维助手。输出：一句结论 + 关键证据 + 建议动作（可执行），简洁中文。"},
            {"role": "user", "content": f"根据结构化建议生成运维总结：{payload}"},
        ]
        llm_summary = llm.chat(messages, temperature=0.2)

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