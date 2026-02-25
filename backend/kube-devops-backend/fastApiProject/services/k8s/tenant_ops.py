# services/k8s_tenant_ops.py
from __future__ import annotations

from typing import Optional

from kubernetes import client
from kubernetes.client import (
    V1Namespace,
    V1ObjectMeta,
    V1ResourceQuota,
    V1RoleBinding,
    V1RoleRef,
)
from kubernetes.client.rest import ApiException

from services.k8s.kube_client import get_core_v1, get_rbac_v1, _load_kube  # ✅ 确保 RBAC 前也 load config


def ensure_namespace(ns: str, labels: Optional[dict] = None):
    api = get_core_v1()

    # 1) 已存在 -> 可选 patch labels
    try:
        api.read_namespace(ns)
        if labels:
            api.patch_namespace(ns, {"metadata": {"labels": labels}})
        return
    except ApiException as e:
        if e.status != 404:
            raise
    except Exception:
        # 其他异常：让上层看到真实错误更好
        raise

    # 2) 不存在 -> create（幂等处理 409）
    body = V1Namespace(metadata=V1ObjectMeta(name=ns, labels=labels or {}))
    try:
        api.create_namespace(body)
    except ApiException as e:
        if e.status != 409:
            raise


def delete_namespace(ns: str):
    api = get_core_v1()
    try:
        api.delete_namespace(ns)
    except ApiException as e:
        # 幂等：不存在也算成功
        if e.status != 404:
            raise


def ensure_rolebinding_admin(namespace: str, username: str):
    """
    绑定 ClusterRole "admin" 到该 namespace 下的 User
    ✅ 关键修复：RBAC client 前显式 _load_kube()，避免未加载 kube config
    """
    _load_kube()
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
    except ApiException as e:
        if e.status == 404:
            rbac.create_namespaced_role_binding(namespace=namespace, body=body)
        else:
            raise


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
        ),
    )

    try:
        api.read_namespaced_resource_quota(name=name, namespace=namespace)
        api.patch_namespaced_resource_quota(name=name, namespace=namespace, body=body)
    except ApiException as e:
        if e.status == 404:
            api.create_namespaced_resource_quota(namespace=namespace, body=body)
        else:
            raise
