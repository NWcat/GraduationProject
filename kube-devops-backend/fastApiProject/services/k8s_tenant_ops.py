# services/k8s_tenant_ops.py
from __future__ import annotations
from typing import Optional

from kubernetes import client
from kubernetes.client import V1ObjectMeta, V1Namespace, V1RoleBinding, V1RoleRef, V1ResourceQuota
from services.kube_client import get_core_v1, get_rbac_v1


def ensure_namespace(ns: str, labels: Optional[dict] = None):
    api = get_core_v1()
    try:
        api.read_namespace(ns)
        # patch labels
        if labels:
            api.patch_namespace(ns, {"metadata": {"labels": labels}})
        return
    except Exception:
        pass

    body = V1Namespace(metadata=V1ObjectMeta(name=ns, labels=labels or {}))
    api.create_namespace(body)

def delete_namespace(ns: str):
    api = get_core_v1()
    api.delete_namespace(ns)

def ensure_rolebinding_admin(namespace: str, username: str):
    # 绑定 ClusterRole "admin" 到该 namespace 下的 User
    rbac = get_rbac_v1()
    name = "tenant-admin-binding"
    body = V1RoleBinding(
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        role_ref=V1RoleRef(api_group="rbac.authorization.k8s.io", kind="ClusterRole", name="admin"),
        subjects=[
            {
                "kind": "User",
                "name": username,
                "apiGroup": "rbac.authorization.k8s.io",
            }
        ],
    )
    try:
        rbac.read_namespaced_role_binding(name=name, namespace=namespace)
        rbac.patch_namespaced_role_binding(name=name, namespace=namespace, body=body)
    except Exception:
        rbac.create_namespaced_role_binding(namespace=namespace, body=body)

def apply_resource_quota(namespace: str, cpu: str, memory: str):
    api = get_core_v1()
    name = "tenant-quota"
    body = V1ResourceQuota(
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=client.V1ResourceQuotaSpec(
            hard={
                "requests.cpu": cpu,
                "requests.memory": memory,
                "limits.cpu": cpu,
                "limits.memory": memory,
            }
        )
    )
    try:
        api.read_namespaced_resource_quota(name=name, namespace=namespace)
        api.patch_namespaced_resource_quota(name=name, namespace=namespace, body=body)
    except Exception:
        api.create_namespaced_resource_quota(namespace=namespace, body=body)