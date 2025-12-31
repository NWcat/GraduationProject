# routers/overview.py
from fastapi import APIRouter
from datetime import datetime, timezone

from services.kube_client import get_cluster_counts
from services.alert_client import list_alerts
from services.prometheus_client import instant_value

router = APIRouter(prefix="/api", tags=["overview"])


def r1(v: float | None) -> float:
    """统一保留 1 位小数，防 Prometheus 抖动 / None"""
    return round(v or 0.0, 1)


@router.get("/overview")
def get_overview():
    # ===============================
    # 1. Kubernetes 资源统计
    # ===============================
    counts = get_cluster_counts()

    # ===============================
    # 2. 告警统计（Alertmanager）
    # ===============================
    try:
        alerts = list_alerts() or []
    except Exception:
        alerts = []

    firing = sum(
        1 for a in alerts
        if (a.get("status") or {}).get("state") == "active"
    )

    # ===============================
    # 3. Prometheus 使用率（集群级）
    # ===============================

    # CPU 使用率（%）
    cpu_usage = instant_value("""
    100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))
    """)

    # 内存使用率（%）—— 容器视角 / 节点总内存
    memory_usage = instant_value("""
    100 *
    sum(container_memory_working_set_bytes{container!="",pod!=""})
    /
    sum(node_memory_MemTotal_bytes)
    """)

    # 存储使用率（%）—— 宿主机磁盘（过滤 pseudo FS）
    storage_usage = instant_value("""
    100 *
    (
      1 -
      sum(node_filesystem_avail_bytes{
        fstype!~"tmpfs|overlay|squashfs|nsfs"
      })
      /
      sum(node_filesystem_size_bytes{
        fstype!~"tmpfs|overlay|squashfs|nsfs"
      })
    )
    """)

    # 网络吞吐（MB/s）—— 非百分比
    network_throughput = instant_value("""
    (
      sum(rate(node_network_receive_bytes_total{device!="lo"}[5m])) +
      sum(rate(node_network_transmit_bytes_total{device!="lo"}[5m]))
    ) / 1024 / 1024
    """)

    # 数值规整
    cpu_usage = r1(cpu_usage)
    memory_usage = r1(memory_usage)
    storage_usage = r1(storage_usage)
    network_throughput = r1(network_throughput)

    # ===============================
    # 4. 返回 BFF 聚合视图模型
    # ===============================
    return {
        "overviewStats": [
            {"key": "nodes", "label": "节点", "value": counts["nodes"]},
            {"key": "namespaces", "label": "命名空间", "value": counts["namespaces"]},
            {"key": "pods", "label": "Pod", "value": counts["pods"]},
            {"key": "services", "label": "Service", "value": counts["services"]},
            {"key": "workloads", "label": "工作负载", "value": counts["workloads"]},
            {
                "key": "alerts24h",
                "label": "告警",
                "value": firing,
                "desc": "当前活跃告警",
            },
        ],
        "capacityStats": [
            {
                "key": "cpu",
                "label": "CPU 使用率",
                "value": cpu_usage,
                "unit": "%",
                "desc": "集群 CPU 整体忙碌程度",
            },
            {
                "key": "memory",
                "label": "内存使用率",
                "value": memory_usage,
                "unit": "%",
                "desc": "容器实际内存使用占节点总内存比例",
            },
            {
                "key": "storage",
                "label": "存储使用率",
                "value": storage_usage,
                "unit": "%",
                "desc": "宿主机磁盘空间使用情况",
            },
            {
                "key": "network",
                "label": "网络吞吐",
                "value": network_throughput,
                "unit": "MB/s",
                "desc": "集群网络实时吞吐速率",
            },
        ],
        "opsSummary": [
            {
                "title": f"当前有 {firing} 条告警",
                "desc": "来自 Alertmanager",
                "level": "warn" if firing > 0 else "ok",
            }
        ],
        "cluster": {
            "basic": {
                "name": "host",
                "status": "running",
                "clusterType": "K3s",
                "k8sVersion": "v1.28.x",
                "platformVersion": "v1.0.0-rc.1",
                "location": "本地实验环境",
            },
            "resources": {
                "nodes": counts["nodes"],
                "namespaces": counts["namespaces"],
                "pods": counts["pods"],
                "alertRules": firing,
            },
            "health": [
                {"level": "ok", "text": "API Server 正常"},
                {"level": "ok", "text": "Scheduler 正常"},
            ],
        },
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
