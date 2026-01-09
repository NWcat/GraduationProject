# routers/tools_kubectl.py
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import settings


router = APIRouter(prefix="/api/tools/k8s", tags=["tools-k8s"])

# -----------------------------
# kubectl exec (read-only only)
# -----------------------------
# 只读子命令：get/describe/logs/top
ALLOWED_KUBECTL_VERBS = {"get", "describe", "logs", "top"}

# 禁止高风险子命令 & 参数（防止绕过 kubeconfig / server / token）
BLOCKLIST_TOKENS = {
    "proxy",
    "port-forward",
    "exec",
    "attach",
    "cp",
    "auth",
    "config",
    "kustomize",
    "apply",
    "delete",
    "rollout",
    "scale",
    "patch",
    "edit",
    "create",
    "replace",
}

BLOCKLIST_FLAGS_PREFIX = {
    "--kubeconfig",
    "--server",
    "--token",
    "--certificate-authority",
    "--client-certificate",
    "--client-key",
    "--username",
    "--password",
    "--context",
    "--user",
    "--cluster",
}


class KubectlExecIn(BaseModel):
    command: str = Field(..., description="不带 kubectl 前缀，例如：get pods -A")
    namespace: Optional[str] = None
    timeout_seconds: int = Field(8, ge=1, le=30)
    output: Literal["text", "json", "yaml"] = "text"


class KubectlExecOut(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


# -----------------------------
# runtime_config helpers
# -----------------------------
def _get_runtime_value(key: str):
    """
    DB 覆盖优先 -> 否则回落 settings/.env
    即使 runtime_config 不可用也不会影响运行。
    """
    try:
        from services.ops.runtime_config import get_value  # type: ignore

        return get_value(key)  # (value, source)
    except Exception:
        return getattr(settings, key, None), "env"


def _get_str(key: str) -> str:
    v, _ = _get_runtime_value(key)
    return str(v or "").strip()


def _get_kube_mode() -> str:
    mode = _get_str("KUBE_MODE") or str(getattr(settings, "KUBE_MODE", "auto") or "auto")
    if mode not in ("auto", "kubeconfig", "incluster"):
        return "auto"
    return mode


def _get_kubeconfig_path() -> str:
    return _get_str("KUBECONFIG_PATH") or str(getattr(settings, "KUBECONFIG_PATH", "") or "").strip()


def _get_kubectl_bin() -> str:
    return _get_str("KUBECTL_BIN") or str(getattr(settings, "KUBECTL_BIN", "") or "").strip()


# -----------------------------
# Python Kubernetes client setup
# -----------------------------
_core_v1 = None
_apps_v1 = None
_custom_api = None
_cfg_loaded = False


def _load_kube_config_once() -> None:
    """
    auto/kubeconfig/incluster 三模式加载一次，供本 router 内 Python client 使用。
    """
    global _cfg_loaded
    if _cfg_loaded:
        return

    try:
        from kubernetes import config  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"kubernetes python client 未安装：{e}")

    mode = _get_kube_mode()
    kubeconfig_path = _get_kubeconfig_path()

    # auto：优先 incluster，失败再 kubeconfig
    if mode == "auto":
        try:
            config.load_incluster_config()
            _cfg_loaded = True
            return
        except Exception:
            pass
        # fallback to kubeconfig
        if kubeconfig_path:
            try:
                config.load_kube_config(config_file=kubeconfig_path)
                _cfg_loaded = True
                return
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"load_kube_config 失败：{e}")
        raise HTTPException(status_code=500, detail="KUBE_MODE=auto 但无法 incluster，且未配置 KUBECONFIG_PATH")

    if mode == "incluster":
        try:
            config.load_incluster_config()
            _cfg_loaded = True
            return
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"load_incluster_config 失败：{e}")

    # kubeconfig
    if mode == "kubeconfig":
        if not kubeconfig_path:
            raise HTTPException(status_code=500, detail="KUBE_MODE=kubeconfig 但 KUBECONFIG_PATH 未配置")
        try:
            config.load_kube_config(config_file=kubeconfig_path)
            _cfg_loaded = True
            return
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"load_kube_config 失败：{e}")

    raise HTTPException(status_code=500, detail=f"unknown KUBE_MODE={mode}")


def _core() :
    global _core_v1
    if _core_v1 is None:
        _load_kube_config_once()
        from kubernetes import client  # type: ignore
        _core_v1 = client.CoreV1Api()
    return _core_v1


def _apps():
    global _apps_v1
    if _apps_v1 is None:
        _load_kube_config_once()
        from kubernetes import client  # type: ignore
        _apps_v1 = client.AppsV1Api()
    return _apps_v1


def _custom():
    global _custom_api
    if _custom_api is None:
        _load_kube_config_once()
        from kubernetes import client  # type: ignore
        _custom_api = client.CustomObjectsApi()
    return _custom_api


def _sa_namespace() -> Optional[str]:
    # incluster 常见路径
    p = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    try:
        if os.path.exists(p):
            return open(p, "r", encoding="utf-8").read().strip() or None
    except Exception:
        return None
    return None


# -----------------------------
# Python-client endpoints
# -----------------------------
@router.get("/whoami")
def whoami():
    """
    返回当前连接模式、kubeconfig、以及 in-cluster namespace（若存在）。
    """
    mode = _get_kube_mode()
    kubeconfig_path = _get_kubeconfig_path() or None
    ns = _sa_namespace()

    # 尝试访问一次 API，验证连通性
    try:
        v1 = _core()
        _ = v1.list_namespace(limit=1)
        ok = True
        err = ""
    except Exception as e:
        ok = False
        err = str(e)

    return {
        "ok": ok,
        "error": err,
        "kube_mode": mode,
        "kubeconfig": kubeconfig_path,
        "incluster_namespace": ns,
        "source": {
            "KUBE_MODE": _get_runtime_value("KUBE_MODE")[1],
            "KUBECONFIG_PATH": _get_runtime_value("KUBECONFIG_PATH")[1],
        },
    }


@router.get("/pods")
def list_pods(namespace: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=2000)):
    v1 = _core()
    items = []
    try:
        if namespace:
            pods = v1.list_namespaced_pod(namespace=namespace, limit=limit).items
        else:
            pods = v1.list_pod_for_all_namespaces(limit=limit).items

        for p in pods:
            phase = getattr(p.status, "phase", "") or ""
            reason = getattr(p.status, "reason", "") or ""
            # container statuses 里取一个更直观的 reason
            cs = getattr(p.status, "container_statuses", None) or []
            c_reason = ""
            for c in cs:
                st = getattr(c, "state", None)
                if st and getattr(st, "waiting", None) and getattr(st.waiting, "reason", None):
                    c_reason = str(st.waiting.reason)
                    break

            owner_kind = ""
            owner_name = ""
            try:
                owners = getattr(p.metadata, "owner_references", None) or []
                if owners:
                    owner_kind = owners[0].kind or ""
                    owner_name = owners[0].name or ""
            except Exception:
                pass

            items.append(
                {
                    "namespace": p.metadata.namespace,
                    "name": p.metadata.name,
                    "uid": p.metadata.uid,
                    "node": p.spec.node_name,
                    "phase": phase,
                    "reason": c_reason or reason,
                    "start_time": (p.status.start_time.isoformat() if p.status.start_time else None),
                    "owner_kind": owner_kind,
                    "owner_name": owner_name,
                    "labels": p.metadata.labels or {},
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "count": len(items), "items": items}


@router.get("/nodes")
def list_nodes(limit: int = Query(200, ge=1, le=2000)):
    v1 = _core()
    out = []
    try:
        nodes = v1.list_node(limit=limit).items
        for n in nodes:
            # ready condition
            ready = "Unknown"
            for c in (n.status.conditions or []):
                if c.type == "Ready":
                    ready = c.status
                    break
            out.append(
                {
                    "name": n.metadata.name,
                    "uid": n.metadata.uid,
                    "ready": ready,
                    "labels": n.metadata.labels or {},
                    "taints": [t.to_dict() for t in (n.spec.taints or [])] if getattr(n.spec, "taints", None) else [],
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "count": len(out), "items": out}


@router.get("/describe/pod")
def describe_pod(namespace: str = Query(...), name: str = Query(...)):
    v1 = _core()
    try:
        pod = v1.read_namespaced_pod(name=name, namespace=namespace)
        # 事件（可选）
        events = []
        try:
            evs = v1.list_namespaced_event(namespace=namespace, field_selector=f"involvedObject.name={name}").items
            for e in evs:
                events.append(
                    {
                        "type": e.type,
                        "reason": e.reason,
                        "message": e.message,
                        "count": e.count,
                        "first_timestamp": (e.first_timestamp.isoformat() if e.first_timestamp else None),
                        "last_timestamp": (e.last_timestamp.isoformat() if e.last_timestamp else None),
                    }
                )
        except Exception:
            pass

        return {
            "ok": True,
            "pod": pod.to_dict(),
            "events": events,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/pod")
def pod_logs(
    namespace: str = Query(...),
    name: str = Query(...),
    container: Optional[str] = Query(None),
    tail_lines: int = Query(200, ge=1, le=5000),
    since_seconds: Optional[int] = Query(None, ge=1, le=24 * 3600),
):
    v1 = _core()
    try:
        text = v1.read_namespaced_pod_log(
            name=name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
            since_seconds=since_seconds,
            timestamps=True,
        )
        return {"ok": True, "stdout": text or ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top/pod")
def top_pod(namespace: str = Query(...), name: str = Query(...)):
    """
    通过 metrics.k8s.io 读取 Pod metrics（需要集群装 metrics-server）。
    没装就返回 501（不算错误，属于能力缺失）。
    """
    api = _custom()
    try:
        data = api.get_namespaced_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="pods",
            name=name,
        )
        return {"ok": True, "metrics": data}
    except Exception as e:
        # 很常见：没装 metrics-server / RBAC 不允许
        raise HTTPException(status_code=501, detail=f"metrics 不可用（需要 metrics-server / RBAC）：{e}")


# -----------------------------
# kubectl exec (read-only)
# -----------------------------
def _resolve_kubectl_path() -> str:
    kb = _get_kubectl_bin()
    if kb:
        p = Path(kb)
        if not p.exists():
            raise HTTPException(status_code=500, detail=f"kubectl 不存在：{p}")
        return str(p)
    return "kubectl"


def _check_kubectl_command_safe(tokens: List[str]) -> None:
    if not tokens:
        raise HTTPException(status_code=400, detail="command 不能为空")

    verb = tokens[0].lower()
    if verb not in ALLOWED_KUBECTL_VERBS:
        raise HTTPException(status_code=400, detail=f"只读限制：仅允许 {sorted(list(ALLOWED_KUBECTL_VERBS))}")

    lowered = {t.lower() for t in tokens}
    if lowered & BLOCKLIST_TOKENS:
        raise HTTPException(status_code=400, detail="命令包含被禁止的操作（安全限制）")

    # 禁止覆盖凭据/集群
    for t in tokens:
        tl = t.lower()
        for pref in BLOCKLIST_FLAGS_PREFIX:
            if tl == pref or tl.startswith(pref + "="):
                raise HTTPException(status_code=400, detail=f"禁止参数：{pref}")

    # 禁止 shell 拼接
    joined = " ".join(tokens)
    bad_chars = {";", "&&", "||", "|", "`"}
    if any(x in joined for x in bad_chars):
        raise HTTPException(status_code=400, detail="命令包含非法字符（安全限制）")


def _build_kubectl_env_and_base(kubectl: str) -> tuple[List[str], Dict[str, str]]:
    env = os.environ.copy()
    env.pop("KUBERNETES_MASTER", None)
    env.pop("KUBE_MASTER", None)

    kubeconfig_path = _get_kubeconfig_path()
    mode = _get_kube_mode()

    base = [kubectl]

    if kubeconfig_path:
        base += ["--kubeconfig", kubeconfig_path]
        env["KUBECONFIG"] = kubeconfig_path
        return base, env

    # 没 kubeconfig：允许 incluster 继续（但 kubectl 本身仍可能不可用/不可连）
    if mode == "incluster":
        return base, env

    raise HTTPException(status_code=500, detail="KUBECONFIG_PATH 未配置（且未启用 incluster）")


@router.post("/kubectl/exec", response_model=KubectlExecOut)
def kubectl_exec(payload: KubectlExecIn):
    """
    只读 kubectl 工具箱：get/describe/logs/top
    （平台核心动作请用 Python client/ops_actions 链路）
    """
    try:
        tokens = shlex.split(payload.command, posix=(os.name != "nt"))
    except ValueError:
        raise HTTPException(status_code=400, detail="命令解析失败：引号不匹配？")

    _check_kubectl_command_safe(tokens)

    kubectl = _resolve_kubectl_path()
    base, env = _build_kubectl_env_and_base(kubectl)

    cmd = base + tokens

    # 输出格式（只读也允许 -o）
    if payload.output in ("json", "yaml") and "-o" not in tokens:
        cmd += ["-o", payload.output]

    # namespace（-A 时不加）
    if (
        payload.namespace
        and "-n" not in tokens
        and "--namespace" not in tokens
        and "-A" not in tokens
        and "--all-namespaces" not in tokens
    ):
        cmd += ["-n", payload.namespace]

    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=payload.timeout_seconds,
            check=False,
            env=env,
        )
        return KubectlExecOut(
            ok=(p.returncode == 0),
            stdout=p.stdout or "",
            stderr=p.stderr or "",
            exit_code=p.returncode,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="kubectl 未找到：请设置 KUBECTL_BIN 或确保 PATH 中存在 kubectl")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="kubectl 执行超时")
