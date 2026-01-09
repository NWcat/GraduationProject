# services/workloads_services.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from kubernetes import client
from kubernetes.client import ApiClient
import yaml as pyyaml

from services.kube_client import get_core_v1, get_apps_v1  # ✅ 改这里：用 getter
from kubernetes.client import V1DeleteOptions

Kind = Literal["deployment", "statefulset", "pod"]
RowStatus = Literal["running", "warning", "failed", "unknown"]


def _utc_now():
    return datetime.now(timezone.utc)


def _age_str(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    delta = _utc_now() - dt
    sec = int(delta.total_seconds())
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec//60}m"
    if sec < 86400:
        return f"{sec//3600}h"
    return f"{sec//86400}d"


def _fmt_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def list_namespaces() -> list[str]:
    api = get_core_v1()
    nss = api.list_namespace().items
    return sorted([x.metadata.name for x in nss if x.metadata and x.metadata.name])


def _match_keyword(hay: str, keyword: Optional[str]) -> bool:
    if not keyword:
        return True
    return keyword.lower() in (hay or "").lower()


def _status_deployment(obj: client.V1Deployment) -> RowStatus:
    spec = obj.spec
    st = obj.status
    replicas = (spec.replicas or 0) if spec else 0
    ready = (st.ready_replicas or 0) if st else 0
    available = (st.available_replicas or 0) if st else 0

    if replicas == 0:
        return "running"
    if ready == replicas and available == replicas:
        return "running"
    return "warning"


def _status_statefulset(obj: client.V1StatefulSet) -> RowStatus:
    spec = obj.spec
    st = obj.status
    replicas = (spec.replicas or 0) if spec else 0
    ready = (st.ready_replicas or 0) if st else 0

    if replicas == 0:
        return "running"
    return "running" if ready == replicas else "warning"


def _pod_ready(p: client.V1Pod) -> bool:
    if not p.status or not p.status.conditions:
        return False
    for c in p.status.conditions:
        if c.type == "Ready" and c.status == "True":
            return True
    return False


def _status_pod(p: client.V1Pod) -> RowStatus:
    phase = (p.status.phase or "Unknown") if p.status else "Unknown"
    if phase == "Running":
        return "running" if _pod_ready(p) else "warning"
    if phase in ("Pending",):
        return "warning"
    if phase in ("Failed",):
        return "failed"
    if phase in ("Succeeded",):
        return "running"
    return "unknown"


def _images_from_pod_template(spec) -> str:
    if not spec or not spec.containers:
        return "-"
    imgs = []
    for c in spec.containers:
        if c.image and c.image not in imgs:
            imgs.append(c.image)
    return ", ".join(imgs) if imgs else "-"


def list_deployments(namespace: Optional[str], status: Optional[RowStatus], keyword: Optional[str]):
    apps = get_apps_v1()

    if namespace:
        items = apps.list_namespaced_deployment(namespace=namespace).items
    else:
        items = apps.list_deployment_for_all_namespaces().items

    out = []
    for d in items:
        ns = d.metadata.namespace
        name = d.metadata.name

        st = _status_deployment(d)
        if status and st != status:
            continue

        img = _images_from_pod_template(d.spec.template.spec if d.spec and d.spec.template else None)
        hay = " ".join([name or "", ns or "", img])
        if not _match_keyword(hay, keyword):
            continue

        replicas = d.spec.replicas or 0
        ready = d.status.ready_replicas or 0
        strategy = (d.spec.strategy.type if d.spec and d.spec.strategy else "RollingUpdate") or "RollingUpdate"

        out.append({
            "kind": "deployment",
            "kindTag": "Deployment",
            "name": name,
            "namespace": ns,
            "status": st,
            "image": img,
            "age": _age_str(d.metadata.creation_timestamp),
            "replicas": replicas,
            "readyReplicas": ready,
            "strategy": strategy,
            "updatedAt": _fmt_time(d.metadata.creation_timestamp),
        })

    return out


def list_statefulsets(namespace: Optional[str], status: Optional[RowStatus], keyword: Optional[str]):
    apps = get_apps_v1()

    if namespace:
        items = apps.list_namespaced_stateful_set(namespace=namespace).items
    else:
        items = apps.list_stateful_set_for_all_namespaces().items

    out = []
    for s in items:
        ns = s.metadata.namespace
        name = s.metadata.name

        st = _status_statefulset(s)
        if status and st != status:
            continue

        img = _images_from_pod_template(s.spec.template.spec if s.spec and s.spec.template else None)
        hay = " ".join([name or "", ns or "", img])
        if not _match_keyword(hay, keyword):
            continue

        replicas = s.spec.replicas or 0
        ready = s.status.ready_replicas or 0
        strategy = "RollingUpdate"
        if s.spec and s.spec.update_strategy and s.spec.update_strategy.type:
            strategy = s.spec.update_strategy.type

        out.append({
            "kind": "statefulset",
            "kindTag": "StatefulSet",
            "name": name,
            "namespace": ns,
            "status": st,
            "image": img,
            "age": _age_str(s.metadata.creation_timestamp),
            "replicas": replicas,
            "readyReplicas": ready,
            "strategy": strategy,
            "updatedAt": _fmt_time(s.metadata.creation_timestamp),
        })

    return out


def list_pods(namespace: Optional[str], status: Optional[RowStatus], keyword: Optional[str]):
    api = get_core_v1()

    if namespace:
        items = api.list_namespaced_pod(namespace=namespace).items
    else:
        items = api.list_pod_for_all_namespaces().items

    out = []
    for p in items:
        ns = p.metadata.namespace
        name = p.metadata.name

        st = _status_pod(p)
        if status and st != status:
            continue

        img = _images_from_pod_template(p.spec)
        node = p.spec.node_name if p.spec else ""
        pod_ip = p.status.pod_ip if p.status else ""
        restarts = 0
        if p.status and p.status.container_statuses:
            restarts = sum((cs.restart_count or 0) for cs in p.status.container_statuses)

        hay = " ".join([name or "", ns or "", img, node or "", pod_ip or ""])
        if not _match_keyword(hay, keyword):
            continue

        out.append({
            "kind": "pod",
            "kindTag": "Pod",
            "name": name,
            "namespace": ns,
            "status": st,
            "image": img,
            "age": _age_str(p.metadata.creation_timestamp),
            "node": node,
            "podIP": pod_ip,
            "restarts": restarts,
            "createdAt": _fmt_time(p.metadata.creation_timestamp),
        })

    return out


def get_resource_yaml(kind: Kind, namespace: str, name: str) -> str:
    api = get_core_v1()
    apps = get_apps_v1()

    if kind == "deployment":
        obj = apps.read_namespaced_deployment(name=name, namespace=namespace)
    elif kind == "statefulset":
        obj = apps.read_namespaced_stateful_set(name=name, namespace=namespace)
    else:
        obj = api.read_namespaced_pod(name=name, namespace=namespace)

    api_client = ApiClient()
    data = api_client.sanitize_for_serialization(obj)
    return pyyaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def scale_workload(kind: Literal["deployment", "statefulset"], namespace: str, name: str, replicas: int):
    apps = get_apps_v1()
    body = {"spec": {"replicas": replicas}}
    if kind == "deployment":
        apps.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)
    else:
        apps.patch_namespaced_stateful_set_scale(name=name, namespace=namespace, body=body)


def restart_workload(kind: Literal["deployment", "statefulset"], namespace: str, name: str):
    apps = get_apps_v1()

    ts = datetime.now(timezone.utc).isoformat()
    patch = {
        "spec": {
            "template": {
                "metadata": {"annotations": {"kubeguard/restartedAt": ts}}
            }
        }
    }

    if kind == "deployment":
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
    else:
        apps.patch_namespaced_stateful_set(name=name, namespace=namespace, body=patch)


def delete_pod(namespace: str, name: str):
    api = get_core_v1()
    api.delete_namespaced_pod(name=name, namespace=namespace)


def get_pod_logs(namespace: str, name: str, container: Optional[str], tail_lines: int = 200) -> str:
    api = get_core_v1()
    return api.read_namespaced_pod_log(
        name=name,
        namespace=namespace,
        container=container,
        tail_lines=tail_lines,
        timestamps=True,
    )
def delete_workload(
    kind: Literal["deployment", "statefulset"],
    namespace: str,
    name: str,
    delete_pvc: bool = False,
):
    apps = get_apps_v1()
    api = get_core_v1()

    # 级联删除：Foreground（更“彻底”，会等子资源清理）
    delete_opts = V1DeleteOptions(
        propagation_policy="Foreground",
        grace_period_seconds=0,
    )

    if kind == "deployment":
        apps.delete_namespaced_deployment(
            name=name,
            namespace=namespace,
            body=delete_opts,
        )
        return

    # statefulset
    apps.delete_namespaced_stateful_set(
        name=name,
        namespace=namespace,
        body=delete_opts,
    )

    # ✅ 可选：清理 PVC（危险）
    if delete_pvc:
        # 常见约定：PVC label app=<sts-name> 或者 statefulset.kubernetes.io/pod-name
        # 这里用 selector 尽量覆盖：app=<name>（你模板里就是这个）
        # 如果你真实环境不是这个 label，请按你的 label 调整 selector
        selector = f"app={name}"
        pvcs = api.list_namespaced_persistent_volume_claim(namespace=namespace, label_selector=selector).items

        for pvc in pvcs:
            if pvc.metadata and pvc.metadata.name:
                api.delete_namespaced_persistent_volume_claim(
                    name=pvc.metadata.name,
                    namespace=namespace,
                    body=delete_opts,
                )