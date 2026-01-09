# services/nodes_service.py
from __future__ import annotations

from typing import Any, Dict, List

from kubernetes import client
from kubernetes.client import ApiException

# ✅ 统一用 kube_client 的 getter（避免直接依赖 _load_kube / 手动 new Api）
from services.kube_client import get_core_v1, get_custom_objects  # 你需要在 kube_client.py 提供 get_custom_objects()


def _parse_cpu_to_cores(cpu: str) -> float:
    """
    Kubernetes quantity -> cores
    examples:
      "250m" => 0.25
      "2"    => 2.0
      "100000000n" => 0.1
    """
    s = str(cpu).strip()
    if not s:
        return 0.0
    if s.endswith("m"):
        return float(s[:-1]) / 1000.0
    if s.endswith("n"):
        return float(s[:-1]) / 1_000_000_000.0
    return float(s)


def _parse_mem_to_gb(mem: str) -> float:
    """
    Kubernetes quantity -> GB
    memory typically:
      "123456Ki", "1024Mi", "8Gi"
    """
    s = str(mem).strip()
    if not s:
        return 0.0

    units = [
        ("Ki", 1024),
        ("Mi", 1024**2),
        ("Gi", 1024**3),
        ("Ti", 1024**4),
        ("Pi", 1024**5),
        ("Ei", 1024**6),
        ("K", 1000),
        ("M", 1000**2),
        ("G", 1000**3),
        ("T", 1000**4),
    ]
    for u, base in units:
        if s.endswith(u):
            v = float(s[: -len(u)])
            bytes_val = v * base
            return bytes_val / (1000**3)  # GB(10^9)
    # no unit, treat as bytes
    return float(s) / (1000**3)


def _get_node_role(node: client.V1Node) -> str:
    labels = node.metadata.labels or {}
    if "node-role.kubernetes.io/control-plane" in labels or "node-role.kubernetes.io/master" in labels:
        return "control-plane"
    return "worker"


def _get_node_status(node: client.V1Node) -> str:
    conds = node.status.conditions or []
    for c in conds:
        if c.type == "Ready":
            return "Ready" if c.status == "True" else "NotReady"
    return "NotReady"


def _get_node_ip(node: client.V1Node) -> str:
    addrs = node.status.addresses or []
    internal = ""
    hostname = ""
    for a in addrs:
        if a.type == "InternalIP":
            internal = a.address
        if a.type == "Hostname":
            hostname = a.address
    return internal or hostname or "-"


def _fetch_node_metrics_map() -> Dict[str, Dict[str, str]]:
    """
    从 metrics-server 获取 nodes metrics.
    返回：
      {
        "nodeName": {"cpu": "250m", "memory": "1024Mi"}
      }
    若 metrics-server 不可用，返回空 dict
    """
    co = get_custom_objects()
    try:
        data = co.list_cluster_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            plural="nodes",
        )
    except ApiException:
        return {}
    except Exception:
        return {}

    items = (data.get("items") or []) if isinstance(data, dict) else []
    out: Dict[str, Dict[str, str]] = {}
    for it in items:
        name = (it.get("metadata") or {}).get("name")
        usage = (it.get("usage") or {})
        if name:
            out[str(name)] = {
                "cpu": str(usage.get("cpu", "0")),
                "memory": str(usage.get("memory", "0")),
            }
    return out


def list_nodes() -> List[Dict[str, Any]]:
    """
    给前端 NodeList.vue 用的行数据
    """
    v1 = get_core_v1()

    nodes = v1.list_node().items
    metrics_map = _fetch_node_metrics_map()

    rows: List[Dict[str, Any]] = []

    for n in nodes:
        name = n.metadata.name
        role = _get_node_role(n)
        status = _get_node_status(n)
        ip = _get_node_ip(n)

        node_info = n.status.node_info
        kubelet_version = node_info.kubelet_version if node_info else "-"
        os_image = node_info.os_image if node_info else "-"
        kernel_version = node_info.kernel_version if node_info else "-"
        container_runtime = node_info.container_runtime_version if node_info else "-"

        cap = n.status.capacity or {}
        cpu_total = _parse_cpu_to_cores(cap.get("cpu", "0"))
        mem_total = _parse_mem_to_gb(cap.get("memory", "0"))

        try:
            pod_capacity = int(str(cap.get("pods", "0")))
        except Exception:
            pod_capacity = 0

        mu = metrics_map.get(name)
        if mu:
            cpu_used = _parse_cpu_to_cores(mu.get("cpu", "0"))
            mem_used = _parse_mem_to_gb(mu.get("memory", "0"))
        else:
            cpu_used = 0.0
            mem_used = 0.0

        rows.append(
            {
                "name": name,
                "ip": ip,
                "role": role,
                "status": status,
                "unschedulable": bool(getattr(n.spec, "unschedulable", False)),
                "kubeletVersion": kubelet_version,
                "osImage": os_image,
                "kernelVersion": kernel_version,
                "containerRuntime": container_runtime,
                "cpuTotal": round(cpu_total, 2),
                "cpuUsed": round(cpu_used, 2),
                "memTotal": round(mem_total, 2),
                "memUsed": round(mem_used, 2),
                "podCapacity": pod_capacity,
                "podUsed": 0,
            }
        )

    # podUsed：统计每个节点当前 Running/Pending 的 Pod 数量
    try:
        pods = v1.list_pod_for_all_namespaces(watch=False).items
        cnt: Dict[str, int] = {}
        for p in pods:
            node_name = p.spec.node_name
            if not node_name:
                continue
            phase = (p.status.phase or "") if p.status else ""
            if phase in ("Succeeded", "Failed"):
                continue
            cnt[node_name] = cnt.get(node_name, 0) + 1

        for r in rows:
            r["podUsed"] = cnt.get(r["name"], 0)
    except Exception:
        pass

    return rows
