# services/ops/k8s_api.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.k8s.kubectl_runner import run_kubectl
from services.k8s.kube_client import get_core_v1, get_apps_v1


def _safe_k8s_client_enabled() -> bool:
    try:
        _ = get_core_v1()
        return True
    except Exception:
        return False


def _parse_deployment_from_replicaset(rs_name: str) -> str:
    if not rs_name:
        return "unknown"
    if "-" not in rs_name:
        return rs_name
    return rs_name.rsplit("-", 1)[0]


def _get_deployment_uid_from_rs(namespace: str, rs_name: str) -> str:
    try:
        apps = get_apps_v1()
        rs = apps.read_namespaced_replica_set(name=rs_name, namespace=namespace)
        owners = rs.metadata.owner_references or []
        for o in owners:
            if getattr(o, "kind", None) == "Deployment" and getattr(o, "uid", None):
                return str(o.uid)
        return "unknown"
    except Exception:
        return "unknown"


def list_pods(namespace: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    if _safe_k8s_client_enabled():
        v1 = get_core_v1()
        pods = v1.list_namespaced_pod(namespace=namespace) if namespace else v1.list_pod_for_all_namespaces()

        for p in pods.items:
            controller_kind = None
            controller_name = None
            deployment_name = "unknown"
            deployment_uid = "unknown"

            owners = p.metadata.owner_references or []
            if owners:
                controller_kind = owners[0].kind
                controller_name = owners[0].name

                if controller_kind == "ReplicaSet" and controller_name:
                    deployment_name = _parse_deployment_from_replicaset(controller_name)
                    deployment_uid = _get_deployment_uid_from_rs(p.metadata.namespace, controller_name)

            pod_uid = p.metadata.uid or "unknown"

            container_statuses = []
            for cs in p.status.container_statuses or []:
                container_statuses.append(
                    {
                        "name": cs.name,
                        "restart_count": cs.restart_count,
                        "waiting_reason": (cs.state.waiting.reason if cs.state and cs.state.waiting else None),
                        "state": {
                            "waiting": {"reason": cs.state.waiting.reason} if cs.state and cs.state.waiting else {},
                            "terminated": {"reason": cs.state.terminated.reason} if cs.state and cs.state.terminated else {},
                            "running": {} if cs.state and cs.state.running else {},
                        },
                    }
                )

            out.append(
                {
                    "namespace": p.metadata.namespace,
                    "name": p.metadata.name,
                    "pod_uid": pod_uid,
                    "phase": p.status.phase,
                    "conditions": [{"type": c.type, "status": c.status} for c in (p.status.conditions or [])],
                    "container_statuses": container_statuses,
                    "controller_kind": controller_kind,
                    "controller_name": controller_name,
                    "deployment_name": deployment_name,
                    "deployment_uid": deployment_uid,
                }
            )
        return out

    # fallback: kubectl（可按需补 JSON 解析）
    args = ["get", "pods", "-o", "json"]
    if namespace:
        args += ["-n", namespace]
    run_kubectl(args)
    return []


def delete_pod(namespace: str, name: str) -> str:
    if _safe_k8s_client_enabled():
        v1 = get_core_v1()
        v1.delete_namespaced_pod(name=name, namespace=namespace)
        return "deleted"
    code, out_s, err_s = run_kubectl(["delete", "pod", name, "-n", namespace])
    return (out_s or err_s or "").strip()


def get_deployment_replicas(namespace: str, name: str) -> int:
    """
    ✅ 读取 Deployment 当前 spec.replicas（用于 before/after）
    """
    ns = namespace or "default"
    if _safe_k8s_client_enabled():
        apps = get_apps_v1()
        dep = apps.read_namespaced_deployment(name=name, namespace=ns)
        v = getattr(dep.spec, "replicas", None)
        try:
            return int(v or 0)
        except Exception:
            return 0

    code, out_s, err_s = run_kubectl(["get", "deployment", name, "-n", ns, "-o", "jsonpath={.spec.replicas}"])
    s = (out_s or err_s or "").strip()
    try:
        return int(s)
    except Exception:
        return 0


def scale_deployment(namespace: str, name: str, replicas: int) -> str:
    if _safe_k8s_client_enabled():
        apps = get_apps_v1()
        body = {"spec": {"replicas": replicas}}
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
        return f"scaled to {replicas}"
    code, out_s, err_s = run_kubectl(["scale", "deployment", name, "-n", namespace, f"--replicas={replicas}"])
    return (out_s or err_s or "").strip()


def get_deployment_uid(namespace: str, name: str) -> Optional[str]:
    ns = namespace or "default"
    if _safe_k8s_client_enabled():
        try:
            apps = get_apps_v1()
            dep = apps.read_namespaced_deployment(name=name, namespace=ns)
            return str(dep.metadata.uid or "")
        except Exception:
            return None
    code, out_s, err_s = run_kubectl(["get", "deployment", name, "-n", ns, "-o", "jsonpath={.metadata.uid}"])
    s = (out_s or err_s or "").strip()
    if code != 0 or not s:
        return None
    return s


def deployment_exists(namespace: str, name: str, expected_uid: Optional[str] = None) -> bool:
    if not name or name == "unknown":
        return False
    uid = get_deployment_uid(namespace, name)
    if not uid:
        return False
    if expected_uid and expected_uid != "unknown":
        return str(uid) == str(expected_uid)
    return True


def restart_deployment(namespace: str, name: str) -> str:
    code, out_s, err_s = run_kubectl(["rollout", "restart", f"deployment/{name}", "-n", namespace])
    return (out_s or err_s or "").strip()


# =========================
# ✅ 调整 Deployment 资源（requests/limits）
# =========================
def patch_deployment_resources(
    *,
    namespace: str,
    name: str,
    cpu_request: Optional[str] = None,
    cpu_limit: Optional[str] = None,
    mem_request: Optional[str] = None,
    mem_limit: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    """
    Patch Deployment: spec.template.spec.containers[*].resources.{requests,limits}

    - 只 patch 非空字段
    - 默认对所有 containers 生效（你的平台演示足够；后续可加 container_name 精准 patch）
    - 返回 (detail, data)
    """
    ns = namespace or "default"
    dep = name

    # 规范化：空字符串当 None
    def _norm(s: Optional[str]) -> Optional[str]:
        if s is None:
            return None
        t = str(s).strip()
        return t if t else None

    cpu_request = _norm(cpu_request)
    cpu_limit = _norm(cpu_limit)
    mem_request = _norm(mem_request)
    mem_limit = _norm(mem_limit)

    if not any([cpu_request, cpu_limit, mem_request, mem_limit]):
        raise ValueError("at least one of cpu_request/cpu_limit/mem_request/mem_limit must be provided")

    if _safe_k8s_client_enabled():
        apps = get_apps_v1()
        d = apps.read_namespaced_deployment(name=dep, namespace=ns)

        containers = []
        try:
            containers = list(getattr(d.spec.template.spec, "containers", []) or [])
        except Exception:
            containers = []

        if not containers:
            raise ValueError(f"deployment/{dep} has no containers")

        patched = 0
        for c in containers:
            # c.resources may be None
            res = getattr(c, "resources", None)
            if res is None:
                # kubernetes client model will accept dict too in patch body; here only build patch body
                pass

            # 读取现有值（用于回显 data）
            patched += 1

        # ✅ 用 strategic merge patch：按容器名覆盖 resources
        patch_containers: List[Dict[str, Any]] = []
        for c in containers:
            cname = getattr(c, "name", None) or "container"
            r: Dict[str, Any] = {}
            reqs: Dict[str, Any] = {}
            lims: Dict[str, Any] = {}

            if cpu_request:
                reqs["cpu"] = cpu_request
            if mem_request:
                reqs["memory"] = mem_request
            if cpu_limit:
                lims["cpu"] = cpu_limit
            if mem_limit:
                lims["memory"] = mem_limit

            if reqs:
                r["requests"] = reqs
            if lims:
                r["limits"] = lims

            patch_containers.append({"name": cname, "resources": r})

        body = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": patch_containers,
                    }
                }
            }
        }

        apps.patch_namespaced_deployment(name=dep, namespace=ns, body=body)

        detail = (
            f"patched deployment/{dep} resources in {ns}: "
            f"cpu_request={cpu_request} cpu_limit={cpu_limit} mem_request={mem_request} mem_limit={mem_limit}"
        )
        data = {
            "namespace": ns,
            "name": dep,
            "cpu_request": cpu_request,
            "cpu_limit": cpu_limit,
            "mem_request": mem_request,
            "mem_limit": mem_limit,
            "containers": [pc.get("name") for pc in patch_containers],
        }
        return detail, data

    # fallback: kubectl patch（对所有容器按 name patch）
    # 注意：kubectl 的 merge patch 需要带 containers 数组（按 name 合并）
    patch_containers: List[Dict[str, Any]] = []

    # 获取容器名列表（尽量不引入新依赖：用 jsonpath 拉出来）
    code, out_s, err_s = run_kubectl(
        ["get", "deployment", dep, "-n", ns, "-o", "jsonpath={.spec.template.spec.containers[*].name}"]
    )
    names_str = (out_s or err_s or "").strip()
    names = [x for x in names_str.split() if x.strip()] or ["container"]

    for cname in names:
        r: Dict[str, Any] = {}
        reqs: Dict[str, Any] = {}
        lims: Dict[str, Any] = {}

        if cpu_request:
            reqs["cpu"] = cpu_request
        if mem_request:
            reqs["memory"] = mem_request
        if cpu_limit:
            lims["cpu"] = cpu_limit
        if mem_limit:
            lims["memory"] = mem_limit

        if reqs:
            r["requests"] = reqs
        if lims:
            r["limits"] = lims

        patch_containers.append({"name": cname, "resources": r})

    body = {"spec": {"template": {"spec": {"containers": patch_containers}}}}
    import json

    code, out_s, err_s = run_kubectl(
        ["patch", "deployment", dep, "-n", ns, "--type=merge", "-p", json.dumps(body)]
    )
    s = (out_s or err_s or "").strip() or "patched"

    detail = (
        f"{s} (cpu_request={cpu_request} cpu_limit={cpu_limit} mem_request={mem_request} mem_limit={mem_limit})"
    )
    data = {
        "namespace": ns,
        "name": dep,
        "cpu_request": cpu_request,
        "cpu_limit": cpu_limit,
        "mem_request": mem_request,
        "mem_limit": mem_limit,
        "containers": [pc.get("name") for pc in patch_containers],
    }
    return detail, data
