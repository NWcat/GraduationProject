# routers/tools_kubectl.py
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import settings  # ✅ 用 settings，不用 os.getenv


router = APIRouter(prefix="/api/tools/kubectl", tags=["tools-kubectl"])

ALLOWED_VERBS = {"get", "describe", "logs", "top", "apply", "delete", "rollout", "scale"}
BLOCKLIST_TOKENS = {"proxy", "port-forward", "exec", "attach", "cp", "auth", "config", "kustomize"}


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


def _resolve_kubectl_path() -> str:
    # ✅ 优先用 settings.KUBECTL_BIN（来自 .env）
    if settings.KUBECTL_BIN:
        p = Path(settings.KUBECTL_BIN)
        if not p.exists():
            raise HTTPException(status_code=500, detail=f"kubectl 不存在：{p}")
        return str(p)
    # ✅ 兜底：走 PATH 里的 kubectl
    return "kubectl"


def _check_command_safe(tokens: list[str]) -> None:
    if not tokens:
        raise HTTPException(status_code=400, detail="command 不能为空")

    verb = tokens[0]
    if verb not in ALLOWED_VERBS:
        raise HTTPException(status_code=400, detail=f"不允许的 kubectl 子命令：{verb}")

    lowered = {t.lower() for t in tokens}
    if lowered & BLOCKLIST_TOKENS:
        raise HTTPException(status_code=400, detail="命令包含被禁止的操作（安全限制）")

    bad_chars = {";", "&&", "||", "|", "`"}
    joined = " ".join(tokens)
    if any(x in joined for x in bad_chars):
        raise HTTPException(status_code=400, detail="命令包含非法字符（安全限制）")


@router.get("/whoami")
def whoami():
    kubectl = _resolve_kubectl_path()

    env = os.environ.copy()
    env.pop("KUBERNETES_MASTER", None)  # 防止覆盖到 localhost:8080

    # 强制指定 kubeconfig（双保险：参数 + 环境变量）
    if settings.KUBECONFIG_PATH:
        env["KUBECONFIG"] = settings.KUBECONFIG_PATH

    def run(args: list[str]) -> str:
        base = [kubectl]
        if settings.KUBECONFIG_PATH:
            base += ["--kubeconfig", settings.KUBECONFIG_PATH]
        p = subprocess.run(base + args, capture_output=True, text=True, env=env)
        return (p.stdout or p.stderr or "").strip()

    ctx = run(["config", "current-context"])
    server = run(["config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}"])
    return {
        "kubectl": kubectl,
        "kubeconfig": settings.KUBECONFIG_PATH,
        "current_context": ctx,
        "server": server,
    }


@router.post("/exec", response_model=KubectlExecOut)
def kubectl_exec(payload: KubectlExecIn):
    try:
        tokens = shlex.split(payload.command, posix=(os.name != "nt"))
    except ValueError:
        raise HTTPException(status_code=400, detail="命令解析失败：引号不匹配？")

    _check_command_safe(tokens)

    kubectl = _resolve_kubectl_path()

    # ✅ 统一清理，和 whoami 对齐
    env = os.environ.copy()
    env.pop("KUBERNETES_MASTER", None)
    env.pop("KUBE_MASTER", None)

    cmd = [kubectl]

    # ✅ 只要你配置了 KUBECONFIG_PATH，就无条件强制使用它（最稳）
    if settings.KUBECONFIG_PATH:
        cmd += ["--kubeconfig", settings.KUBECONFIG_PATH]
        env["KUBECONFIG"] = settings.KUBECONFIG_PATH
    else:
        # 没 kubeconfig 才考虑 incluster（你后面部署到集群内再用）
        if settings.KUBE_MODE == "incluster":
            # kubectl 本身不吃 load_incluster_config，但你可以不走 kubectl，
            # 直接用 python client 做 exec/获取资源更安全
            pass
        else:
            raise HTTPException(status_code=500, detail="KUBECONFIG_PATH 未配置，且未启用 incluster")

    cmd += tokens

    # 输出格式
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