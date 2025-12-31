# services/kube_client.py
from __future__ import annotations

import os
from typing import Dict

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

from config import settings

_api: client.CoreV1Api | None = None
_apps: client.AppsV1Api | None = None


def _load_kube():
    """
    ✅ 推荐：KUBE_MODE=auto
    - auto: 先 load_incluster_config()，失败再 load_kube_config()
    - incluster: 只用集群内 ServiceAccount
    - kubeconfig: 只用本地 kubeconfig
    """
    global _api, _apps
    if _api and _apps:
        return

    mode = (getattr(settings, "KUBE_MODE", "auto") or "auto").lower()

    def load_incluster():
        config.load_incluster_config()

    def load_kubeconfig():
        # 依次尝试：KUBECONFIG_PATH -> 环境变量 KUBECONFIG -> 默认 ~/.kube/config
        path = settings.KUBECONFIG_PATH or os.getenv("KUBECONFIG")
        if path:
            config.load_kube_config(config_file=path)
        else:
            config.load_kube_config()

    if mode == "incluster":
        load_incluster()
    elif mode == "kubeconfig":
        load_kubeconfig()
    else:
        # auto
        try:
            load_incluster()
        except Exception:
            load_kubeconfig()

    _api = client.CoreV1Api()
    _apps = client.AppsV1Api()


def get_core_v1() -> client.CoreV1Api:
    _load_kube()
    assert _api is not None
    return _api


def get_apps_v1() -> client.AppsV1Api:
    _load_kube()
    assert _apps is not None
    return _apps


def get_cluster_counts() -> Dict[str, int]:
    """
    用 Kubernetes API 取 Overview 需要的“数量类”数据：
    nodes / namespaces / pods / services / deployments / statefulsets
    """
    _load_kube()
    assert _api is not None and _apps is not None

    nodes = _api.list_node().items
    namespaces = _api.list_namespace().items
    pods = _api.list_pod_for_all_namespaces(watch=False).items
    services = _api.list_service_for_all_namespaces(watch=False).items

    deployments = _apps.list_deployment_for_all_namespaces(watch=False).items
    statefulsets = _apps.list_stateful_set_for_all_namespaces(watch=False).items

    workloads = len(deployments) + len(statefulsets)

    return {
        "nodes": len(nodes),
        "namespaces": len(namespaces),
        "pods": len(pods),
        "services": len(services),
        "workloads": workloads,
        "deployments": len(deployments),
        "statefulsets": len(statefulsets),
    }
def get_rbac_v1():
    return client.RbacAuthorizationV1Api()
