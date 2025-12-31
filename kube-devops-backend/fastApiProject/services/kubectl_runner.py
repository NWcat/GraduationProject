# services/kubectl_runner.py
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException
from config import settings


def _resolve_kubectl() -> str:
    if getattr(settings, "KUBECTL_BIN", None):
        p = Path(settings.KUBECTL_BIN)
        if not p.exists():
            raise HTTPException(status_code=500, detail=f"kubectl 不存在：{p}")
        return str(p)
    return "kubectl"


def kubectl_apply_yaml(yaml_text: str) -> Tuple[int, str, str]:
    """
    用 kubectl apply -f - 应用 YAML（支持多文档）
    """
    kubectl = _resolve_kubectl()

    if not getattr(settings, "KUBECONFIG_PATH", None):
        raise HTTPException(status_code=500, detail="KUBECONFIG_PATH 未配置")

    env = os.environ.copy()
    env["KUBECONFIG"] = settings.KUBECONFIG_PATH
    env.pop("KUBERNETES_MASTER", None)  # 防止 localhost:8080

    cmd = [kubectl, "--kubeconfig", settings.KUBECONFIG_PATH, "apply", "-f", "-"]

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