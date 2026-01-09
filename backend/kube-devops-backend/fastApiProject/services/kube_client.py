# services/kube_client.py
from __future__ import annotations

import os
import threading
from typing import Dict, Tuple

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

from config import settings

_api: client.CoreV1Api | None = None
_apps: client.AppsV1Api | None = None
_custom: client.CustomObjectsApi | None = None
_rbac: client.RbacAuthorizationV1Api | None = None
_policy: client.PolicyV1Api | None = None

_loaded_sig: Tuple[str, str] | None = None

# ✅ 新增：全局锁，避免切换 / 并发初始化竞态
_kube_lock = threading.RLock()


def _reset_clients() -> None:
    global _api, _apps, _custom, _rbac, _policy, _loaded_sig
    _api = None
    _apps = None
    _custom = None
    _rbac = None
    _policy = None
    _loaded_sig = None


def _get_kube_mode() -> str:
    mode = ""
    try:
        from services.ops.runtime_config import get_value  # type: ignore

        v, _src = get_value("KUBE_MODE")
        mode = str(v or "").strip().lower()
    except Exception:
        mode = str(getattr(settings, "KUBE_MODE", "") or "").strip().lower()

    if not mode:
        mode = "auto"
    if mode not in ("auto", "kubeconfig", "incluster"):
        mode = "auto"
    return mode


def _get_kubeconfig_path() -> str:
    path = ""
    try:
        from services.ops.runtime_config import get_value  # type: ignore

        v, _src = get_value("KUBECONFIG_PATH")
        path = str(v or "").strip()
    except Exception:
        path = str(getattr(settings, "KUBECONFIG_PATH", "") or "").strip()

    if not path:
        path = str(os.getenv("KUBECONFIG", "") or "").strip()

    return path


def _sig() -> Tuple[str, str]:
    return (_get_kube_mode(), _get_kubeconfig_path())


def _load_kube() -> None:
    """
    单活多集群：全局只有一个“当前集群 client”
    - 通过 ops_config 覆盖 KUBE_MODE / KUBECONFIG_PATH
    - 检测签名变化则 reset + reload
    """
    global _api, _apps, _custom, _rbac, _policy, _loaded_sig

    with _kube_lock:
        current = _sig()

        # 已初始化：配置没变 => 复用
        if _api is not None and _apps is not None and _loaded_sig == current:
            return

        # 配置变了 or 未初始化
        _reset_clients()

        mode, kubeconfig_path = current

        def load_incluster() -> None:
            config.load_incluster_config()

        def load_kubeconfig() -> None:
            if kubeconfig_path:
                config.load_kube_config(config_file=kubeconfig_path)
            else:
                config.load_kube_config()

        try:
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
        except ConfigException as e:
            raise RuntimeError(
                f"kube config load failed (mode={mode}, kubeconfig={kubeconfig_path or '<default>'}): {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"kube config load failed (mode={mode}, kubeconfig={kubeconfig_path or '<default>'}): {e}"
            )

        _api = client.CoreV1Api()
        _apps = client.AppsV1Api()
        _custom = client.CustomObjectsApi()
        _rbac = client.RbacAuthorizationV1Api()
        _policy = client.PolicyV1Api()
        _loaded_sig = current


def get_core_v1() -> client.CoreV1Api:
    _load_kube()
    assert _api is not None
    return _api


def get_apps_v1() -> client.AppsV1Api:
    _load_kube()
    assert _apps is not None
    return _apps


def get_custom_objects() -> client.CustomObjectsApi:
    _load_kube()
    assert _custom is not None
    return _custom


def get_rbac_v1() -> client.RbacAuthorizationV1Api:
    _load_kube()
    assert _rbac is not None
    return _rbac


def get_policy_v1() -> client.PolicyV1Api:
    _load_kube()
    assert _policy is not None
    return _policy


def get_cluster_counts() -> Dict[str, int]:
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


# ====== ✅ kubeconfig 内容连通性测试（修复 Windows 临时文件问题）======

def validate_kubeconfig_content(kubeconfig_text: str) -> Dict[str, str]:
    """
    用 kubeconfig 内容做一次“最小连通性测试”，不影响全局默认 client。
    返回：{"ok":"1","server":"...","nodes":"N"} / 异常直接 raise。
    """
    import tempfile
    import pathlib

    kubeconfig_text = (kubeconfig_text or "").strip()
    if not kubeconfig_text:
        raise RuntimeError("kubeconfig is empty")

    # ✅ Windows 兼容：delete=False，先写盘再关闭，再 load，再手动删
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    tmp_path = pathlib.Path(tmp.name)
    try:
        tmp.write(kubeconfig_text)
        tmp.flush()
        tmp.close()

        cfg = client.Configuration()
        config.load_kube_config(config_file=str(tmp_path), client_configuration=cfg)

        api_client = client.ApiClient(configuration=cfg)
        v1 = client.CoreV1Api(api_client=api_client)

        nodes = v1.list_node().items
        server = ""
        try:
            server = str(getattr(cfg, "host", "") or "")
        except Exception:
            server = ""

        return {"ok": "1", "server": server, "nodes": str(len(nodes))}
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            # 删除失败不影响校验结果
            pass
