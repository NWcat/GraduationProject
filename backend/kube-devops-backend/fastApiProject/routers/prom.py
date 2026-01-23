# routers/prom.py
from __future__ import annotations

from fastapi import APIRouter, Query, Depends
from typing import Any, Dict

from services.prometheus_client import prom_query, prom_query_range, instant_value
from routers.authz import require_user
from services.promql_guard import validate_promql, validate_range

router = APIRouter(prefix="/api/prom", tags=["Prometheus"])

@router.get("/query", dependencies=[Depends(require_user)])
def query(query: str = Query(..., min_length=1)) -> Dict[str, Any]:
    validate_promql(query)
    return prom_query(query)


@router.get("/query_range", dependencies=[Depends(require_user)])
def query_range(
    query: str = Query(..., min_length=1),
    start: float = Query(...),
    end: float = Query(...),
    step: int = Query(30, ge=1),
) -> Dict[str, Any]:
    validate_promql(query)
    validate_range(start, end, step)
    return prom_query_range(query=query, start=start, end=end, step=step)


@router.get("/overview", dependencies=[Depends(require_user)])
def overview(range: str = Query("15m")) -> Dict[str, Any]:
    """
    总览接口（BFF）
    - 集群健康
    - 集群资源使用率
    - Node TopN（可选）
    - Pod TopN（业务命名空间）
    """

    # ========= range =========
    mapping = {"5m": 5, "15m": 15, "1h": 60, "6h": 360, "24h": 1440}
    minutes = mapping.get(range, 15)

    # ========= 基础健康 =========
    q_prom_up = "sum(up)"
    q_nodes_total = 'count(kube_node_info)'
    q_nodes_ready = 'count(kube_node_status_condition{condition="Ready",status="true"})'
    q_alert_firing = 'sum(ALERTS{alertstate="firing"})'
    q_alert_pending = 'sum(ALERTS{alertstate="pending"})'

    # ========= 集群资源 =========
    q_cpu = '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))'
    q_mem = '100 * (1 - (sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes)))'
    q_fs = '''
    100 * (
      1 -
      sum(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"})
      /
      sum(node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs"})
    )
    '''

    # ========= Pod TopN（业务命名空间） =========
    q_pod_top_cpu = '''
    topk(10,
      sum by (namespace, pod) (
        rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])
      )
    )
    '''

    q_pod_top_mem = '''
    topk(10,
      sum by (namespace, pod) (
        container_memory_working_set_bytes{container!="",pod!=""}
      )
    ) / 1024 / 1024
    '''

    q_pod_top_net = '''
    topk(10,
      sum by (namespace, pod) (
        rate(container_network_receive_bytes_total{pod!=""}[5m]) +
        rate(container_network_transmit_bytes_total{pod!=""}[5m])
      )
    ) / 1024
    '''

    # ========= 即时值 =========
    def to_int(v: float) -> int:
        try:
            return int(v)
        except Exception:
            return 0

    prom_ok = instant_value(q_prom_up, 0.0) > 0

    nodes_total = to_int(instant_value(q_nodes_total, 0.0))
    nodes_ready = to_int(instant_value(q_nodes_ready, 0.0))
    alert_firing = to_int(instant_value(q_alert_firing, 0.0))
    alert_pending = to_int(instant_value(q_alert_pending, 0.0))

    cpu_used = instant_value(q_cpu, 0.0)
    mem_used = instant_value(q_mem, 0.0)
    fs_used = instant_value(q_fs, 0.0)

    # ========= Pod TopN =========
    pod_top_cpu = prom_query(q_pod_top_cpu)
    pod_top_mem = prom_query(q_pod_top_mem)
    pod_top_net = prom_query(q_pod_top_net)

    return {
        "status": "success",
        "data": {
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
            "podTop": {
                "cpu": pod_top_cpu,
                "mem": pod_top_mem,
                "net": pod_top_net,
            },
            "range": {"minutes": minutes},
        },
    }
