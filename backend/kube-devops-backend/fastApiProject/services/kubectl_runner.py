# services/kubectl_runner.py
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Tuple, Optional

from fastapi import HTTPException
from config import settings


def _get_runtime_value(key: str):
    """
    生效优先级：DB override（前端） > settings/.env > default（由 settings 提供默认）
    runtime_config 不可用时回退 settings
    """
    try:
        from services.ops.runtime_config import get_value  # type: ignore

        return get_value(key)  # (value, source)
    except Exception:
        return getattr(settings, key, None), "env"


def _get_str(key: str) -> str:
    v, _ = _get_runtime_value(key)
    return str(v or "").strip()


def _get_kubeconfig_path() -> str:
    return _get_str("KUBECONFIG_PATH")


def _get_kubectl_bin() -> str:
    return _get_str("KUBECTL_BIN")


def _resolve_kubectl() -> str:
    kb = _get_kubectl_bin()
    if kb:
        p = Path(kb)
        if not p.exists():
            raise HTTPException(status_code=500, detail=f"kubectl 不存在：{p}")
        return str(p)
    return "kubectl"


def _build_env_and_prefix() -> tuple[dict, list[str]]:
    """
    返回 (env, prefix_args)
    prefix_args 会包含 --kubeconfig <path>（若存在）
    """
    env = os.environ.copy()
    env.pop("KUBERNETES_MASTER", None)  # 防止 localhost:8080
    env.pop("KUBE_MASTER", None)

    kubeconfig_path = _get_kubeconfig_path()

    if not kubeconfig_path:
        raise HTTPException(status_code=500, detail="KUBECONFIG_PATH 未配置")

    env["KUBECONFIG"] = kubeconfig_path
    return env, ["--kubeconfig", kubeconfig_path]


def kubectl_apply_yaml(yaml_text: str) -> Tuple[int, str, str]:
    """
    用 kubectl apply -f - 应用 YAML（支持多文档）
    """
    kubectl = _resolve_kubectl()
    env, prefix = _build_env_and_prefix()

    cmd = [kubectl] + prefix + ["apply", "-f", "-"]

    p = subprocess.run(
        cmd,
        input=yaml_text,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=25,
    )
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def run_kubectl(args: list[str], timeout: int = 25) -> Tuple[int, str, str]:
    """
    通用 kubectl 执行器
    用于 get / delete / scale / rollout 等命令
    """
    kubectl = _resolve_kubectl()
    env, prefix = _build_env_and_prefix()

    cmd = [kubectl] + prefix + args

    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=timeout,
    )
    return p.returncode, (p.stdout or ""), (p.stderr or "")
