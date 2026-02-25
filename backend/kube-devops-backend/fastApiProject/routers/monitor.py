# routers/monitor.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Optional

from fastapi import APIRouter, Query

from services.monitoring.prometheus_client import prom_query, range_by_minutes, instant_value

router = APIRouter(prefix="/api/monitor", tags=["Monitor"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(v: float) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


# ---------- humanize helpers ----------
_BYTES_UNITS = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
_RATE_BYTES_UNITS = ["B/s", "KiB/s", "MiB/s", "GiB/s", "TiB/s"]


def human_bytes(x: float, decimals: int = 1) -> str:
    v = float(x)
    if v <= 0:
        return "0 B"
    i = 0
    while v >= 1024 and i < len(_BYTES_UNITS) - 1:
        v /= 1024.0
        i += 1
    fmt = f"{{:.{decimals}f}}"
    return f"{fmt.format(v)} {_BYTES_UNITS[i]}"


def human_bytes_rate(x: float, decimals: int = 1) -> str:
    v = float(x)
    if v <= 0:
        return "0 B/s"
    i = 0
    while v >= 1024 and i < len(_RATE_BYTES_UNITS) - 1:
        v /= 1024.0
        i += 1
    fmt = f"{{:.{decimals}f}}"
    return f"{fmt.format(v)} {_RATE_BYTES_UNITS[i]}"


def human_cpu_cores(x: float) -> str:
    """
    Prometheus container_cpu_usage_seconds_total rate 的结果是 cores（核数）
    常见显示：>=1 用 core；<1 用 mCPU
    """
    v = float(x)
    if v <= 0:
        return "0"
    if v < 1:
        return f"{int(round(v * 1000))} m"
    # 1.0 core, 2.35 cores
    return f"{v:.2f} core"


def _parse_vector_top(
    data: Dict[str, Any],
    *,
    value_text_fn,
) -> List[Dict[str, Any]]:
    """
    Prometheus instant query 返回 vector：
    data.data.result = [{"metric": {...}, "value":[ts, "123"]}, ...]
    """
    out: List[Dict[str, Any]] = []
    results = (data.get("data") or {}).get("result") or []
    for i, r in enumerate(results, start=1):
        metric = r.get("metric") or {}
        raw = (r.get("value") or [None, "0"])[1]
        v = _to_float(raw)
        out.append(
            {
                "rank": i,
                "metric": metric,
                "value": v,
                "valueText": value_text_fn(v),
            }
        )
    return out


def _parse_matrix_series(data: Dict[str, Any], max_points: int = 120) -> List[Tuple[int, float]]:
    """
    query_range matrix：取第一条时间序列用于 sparkline
    返回 [(ts, value), ...]
    """
    results = (data.get("data") or {}).get("result") or []
    if not results:
        return []
    values = results[0].get("values") or []
    values = values[-max_points:]
    out: List[Tuple[int, float]] = []
    for ts, val in values:
        out.append((int(float(ts)), _to_float(val)))
    return out


@router.get("/overview")
def monitor_overview(
    range: str = Query("15m", description="5m|15m|1h|6h|24h"),
) -> Dict[str, Any]:
    """
    大屏总览（BFF）
    - health
    - resource
    - trends (sparklines)
    - top (pod cpu/mem/net) 统一格式化 valueText
    """
    mapping = {"5m": 5, "15m": 15, "1h": 60, "6h": 360, "24h": 1440}
    minutes = mapping.get(range, 15)

    # ========= 健康 =========
    q_prom_up = "sum(up)"
    q_nodes_total = "count(kube_node_info)"
    q_nodes_ready = 'count(kube_node_status_condition{condition="Ready",status="true"})'
    q_alert_firing = 'sum(ALERTS{alertstate="firing"})'
    q_alert_pending = 'sum(ALERTS{alertstate="pending"})'

    prom_ok = instant_value(q_prom_up, 0.0) > 0
    nodes_total = _to_int(instant_value(q_nodes_total, 0.0))
    nodes_ready = _to_int(instant_value(q_nodes_ready, 0.0))
    alert_firing = _to_int(instant_value(q_alert_firing, 0.0))
    alert_pending = _to_int(instant_value(q_alert_pending, 0.0))

    # ========= 资源（集群级 %）=========
    q_cpu = '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))'
    q_mem = '100 * (1 - (sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes)))'
    q_fs = """
    100 * (
      1 -
      sum(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"})
      /
      sum(node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"})
    )
    """

    cpu_used = _to_float(instant_value(q_cpu, 0.0))
    mem_used = _to_float(instant_value(q_mem, 0.0))
    fs_used = _to_float(instant_value(q_fs, 0.0))

    # ========= 趋势（%）=========
    cpu_trend = _parse_matrix_series(range_by_minutes(q_cpu, minutes=minutes, step=max(15, minutes // 30)), 180)
    mem_trend = _parse_matrix_series(range_by_minutes(q_mem, minutes=minutes, step=max(15, minutes // 30)), 180)
    fs_trend = _parse_matrix_series(range_by_minutes(q_fs, minutes=minutes, step=max(30, minutes // 20)), 180)

    # ========= Pod TopN =========
    q_pod_top_cpu = """
    topk(10,
      sum by (namespace, pod) (
        rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])
      )
    )
    """
    q_pod_top_mem = """
    topk(10,
      sum by (namespace, pod) (
        container_memory_working_set_bytes{container!="",pod!=""}
      )
    )
    """
    q_pod_top_net = """
    topk(10,
      sum by (namespace, pod) (
        rate(container_network_receive_bytes_total{pod!=""}[5m]) +
        rate(container_network_transmit_bytes_total{pod!=""}[5m])
      )
    )
    """

    pod_cpu = _parse_vector_top(prom_query(q_pod_top_cpu), value_text_fn=human_cpu_cores)
    pod_mem = _parse_vector_top(prom_query(q_pod_top_mem), value_text_fn=lambda v: human_bytes(v, 1))
    pod_net = _parse_vector_top(prom_query(q_pod_top_net), value_text_fn=lambda v: human_bytes_rate(v, 1))

    return {
        "status": "success",
        "data": {
            "time": {"range": range, "minutes": minutes, "now": _now_iso()},
            "health": {
                "promOk": bool(prom_ok),
                "nodesTotal": nodes_total,
                "nodesReady": nodes_ready,
                "alertFiring": alert_firing,
                "alertPending": alert_pending,
            },
            "resource": {
                "cpuUsedPct": cpu_used,
                "memUsedPct": mem_used,
                "fsUsedPct": fs_used,
            },
            "trends": {
                "cpuUsedPct": cpu_trend,  # [(ts, value)]
                "memUsedPct": mem_trend,
                "fsUsedPct": fs_trend,
            },
            "top": {
                "podCpu": pod_cpu,
                "podMem": pod_mem,
                "podNet": pod_net,
            },
        },
    }
