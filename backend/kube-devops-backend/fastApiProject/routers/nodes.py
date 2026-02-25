# routers/nodes.py
from __future__ import annotations

from fastapi import APIRouter, Query

from services.nodes.service import list_nodes
from services.nodes.ops import remove_node, offline_node, uncordon_node

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.post("/test")
def test_nodes_router():
    return {"ok": True, "msg": "nodes router is alive"}


@router.get("")
def get_nodes():
    """节点列表：GET /api/nodes"""
    return list_nodes()


@router.get("/join-info")
def get_join_info(
    server: str = Query("", description="K3S server url, e.g. https://1.2.3.4:6443"),
    token: str = Query("", description="K3S token"),

    # ✅ 可选：安装参数
    node_ip: str = Query("", description="--node-ip for k3s agent"),
    flannel_iface: str = Query("", description="--flannel-iface, e.g. eth0"),

    # ✅ 可选：固定版本（强烈建议填成和 master 一样）
    k3s_version: str = Query("", description='INSTALL_K3S_VERSION, e.g. "v1.33.3+k3s1"'),
):
    """
    生成 k3s join 命令（仅返回命令，不执行）
    - server/token 必填，否则返回模板
    - node_ip/flannel_iface 可选：生成 INSTALL_K3S_EXEC
    - k3s_version 可选：生成 INSTALL_K3S_VERSION，避免版本漂移
    """
    server = (server or "").strip()
    token = (token or "").strip()
    node_ip = (node_ip or "").strip()
    flannel_iface = (flannel_iface or "").strip()
    k3s_version = (k3s_version or "").strip()

    if not server or not token:
        return {
            "type": "k3s",
            "ok": False,
            "hint": "请提供 server 和 token（可选再填 node_ip / flannel_iface / k3s_version）",
            "command_template": (
                "curl -sfL https://rancher-mirror.rancher.cn/k3s/k3s-install.sh | "
                "INSTALL_K3S_MIRROR=cn "
                'INSTALL_K3S_VERSION="v1.33.3+k3s1" '
                "K3S_URL=<server> K3S_TOKEN=<token> "
                'INSTALL_K3S_EXEC="--node-ip=<node-ip> --flannel-iface=<iface>" '
                "sh -"
            ),
        }

    # ---- 组装 INSTALL_K3S_EXEC（可为空）----
    exec_args: list[str] = []
    if node_ip:
        exec_args.append(f"--node-ip={node_ip}")
    if flannel_iface:
        exec_args.append(f"--flannel-iface={flannel_iface}")

    install_exec_part = ""
    if exec_args:
        install_exec_part = f'INSTALL_K3S_EXEC="{" ".join(exec_args)}" '

    # ---- 组装 INSTALL_K3S_VERSION（可为空）----
    install_version_part = ""
    if k3s_version:
        install_version_part = f'INSTALL_K3S_VERSION="{k3s_version}" '

    cmd = (
        "curl -sfL https://rancher-mirror.rancher.cn/k3s/k3s-install.sh | "
        "INSTALL_K3S_MIRROR=cn "
        f"{install_version_part}"
        f"K3S_URL={server} "
        f"K3S_TOKEN={token} "
        f"{install_exec_part}"
        "sh -"
    )

    return {
        "type": "k3s",
        "ok": True,
        "command": cmd,
        "params": {
            "node_ip": node_ip or None,
            "flannel_iface": flannel_iface or None,
            "k3s_version": k3s_version or None,
        },
    }


@router.post("/{node_name}/offline")
def api_offline_node(
    node_name: str,
    drain: bool = Query(True),
    grace_seconds: int = Query(30, ge=0, le=600),
    timeout_seconds: int = Query(180, ge=30, le=1800),
    force: bool = Query(False),
):
    return offline_node(
        node_name=node_name,
        drain=drain,
        grace_seconds=grace_seconds,
        timeout_seconds=timeout_seconds,
        force=force,
    )


@router.post("/{node_name}/uncordon")
def api_uncordon_node(node_name: str):
    return uncordon_node(node_name)


@router.post("/{node_name}/remove")
def api_remove_node(
    node_name: str,
    grace_seconds: int = Query(30, ge=0, le=600),
    timeout_seconds: int = Query(180, ge=30, le=1800),
    force: bool = Query(False),
):
    return remove_node(
        node_name=node_name,
        grace_seconds=grace_seconds,
        timeout_seconds=timeout_seconds,
        force=force,
    )