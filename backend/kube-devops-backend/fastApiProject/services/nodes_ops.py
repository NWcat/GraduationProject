# services/nodes_ops.py
from __future__ import annotations

import time
from typing import Any, Dict, List

from fastapi import HTTPException
from kubernetes import client
from kubernetes.client import ApiException

from services.kube_client import get_core_v1, get_policy_v1


def cordon_node(node_name: str) -> Dict[str, Any]:
    v1 = get_core_v1()
    try:
        body = {"spec": {"unschedulable": True}}
        v1.patch_node(node_name, body)
        return {"ok": True, "node": node_name, "action": "cordon"}
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"cordon failed: {e}")

def uncordon_node(node_name: str) -> Dict[str, Any]:
    v1 = get_core_v1()
    try:
        body = {"spec": {"unschedulable": False}}
        v1.patch_node(node_name, body)
        return {"ok": True, "node": node_name, "action": "uncordon"}
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"uncordon failed: {e}")


def offline_node(
    node_name: str,
    drain: bool = True,
    grace_seconds: int = 30,
    timeout_seconds: int = 180,
    force: bool = False,
) -> Dict[str, Any]:
    """
    下线节点（推荐默认）：cordon + (可选)drain，不 delete node
    """
    r1 = cordon_node(node_name)
    steps = [r1]

    if drain:
        r2 = drain_node(
            node_name=node_name,
            grace_seconds=grace_seconds,
            timeout_seconds=timeout_seconds,
            force=force,
        )
        steps.append(r2)

    ok = all(s.get("ok") is True for s in steps)
    return {"ok": ok, "steps": steps}


def _is_mirror_pod(p: client.V1Pod) -> bool:
    anns = (p.metadata.annotations or {})
    return "kubernetes.io/config.mirror" in anns


def _owned_by_daemonset(p: client.V1Pod) -> bool:
    owners = p.metadata.owner_references or []
    return any(o.kind == "DaemonSet" for o in owners)


def drain_node(
    node_name: str,
    grace_seconds: int = 30,
    timeout_seconds: int = 180,
    force: bool = False,
) -> Dict[str, Any]:
    v1 = get_core_v1()
    policy = get_policy_v1()

    # 找出该节点上的 pod
    pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items

    evict_list: List[client.V1Pod] = []
    skipped: List[Dict[str, str]] = []

    for p in pods:
        ns = p.metadata.namespace
        name = p.metadata.name

        # mirror pod 跳过
        if _is_mirror_pod(p):
            skipped.append({"ns": ns, "pod": name, "reason": "mirror_pod"})
            continue

        # DaemonSet 跳过
        if _owned_by_daemonset(p):
            skipped.append({"ns": ns, "pod": name, "reason": "daemonset"})
            continue

        # kube-system 默认不动（你也可以改成 allowlist）
        if ns == "kube-system" and not force:
            skipped.append({"ns": ns, "pod": name, "reason": "kube-system (set force=true to override)"})
            continue

        evict_list.append(p)

    # 逐个 eviction
    evicted: List[Dict[str, str]] = []
    errors: List[str] = []

    for p in evict_list:
        ns = p.metadata.namespace
        name = p.metadata.name
        try:
            eviction = client.V1Eviction(
                metadata=client.V1ObjectMeta(name=name, namespace=ns),
                delete_options=client.V1DeleteOptions(grace_period_seconds=grace_seconds),
            )
            policy.create_namespaced_pod_eviction(name=name, namespace=ns, body=eviction)
            evicted.append({"ns": ns, "pod": name})
        except ApiException as e:
            errors.append(f"evict {ns}/{name} failed: {e}")

    # 等待 pod 真正消失
    start = time.time()
    while time.time() - start < timeout_seconds:
        left = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
        # 只看我们“想驱逐”的那批
        left_names = {(p.metadata.namespace, p.metadata.name) for p in left}
        still = [x for x in evicted if (x["ns"], x["pod"]) in left_names]
        if not still:
            break
        time.sleep(2)

    return {
        "ok": len(errors) == 0,
        "node": node_name,
        "action": "drain",
        "evicted": evicted,
        "skipped": skipped,
        "errors": errors,
    }


def delete_node(node_name: str) -> Dict[str, Any]:
    v1 = get_core_v1()
    try:
        v1.delete_node(node_name)
        return {"ok": True, "node": node_name, "action": "delete"}
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"delete node failed: {e}")


def remove_node(
    node_name: str,
    grace_seconds: int = 30,
    timeout_seconds: int = 180,
    force: bool = False,
) -> Dict[str, Any]:
    """
    完全移除（集群侧）：cordon -> drain -> delete node
    注意：不会卸载节点上的 k3s-agent。若 agent 仍在运行且能连 server，节点可能会再次注册回来。
    """
    r1 = cordon_node(node_name)

    r2 = drain_node(
        node_name=node_name,
        grace_seconds=grace_seconds,
        timeout_seconds=timeout_seconds,
        force=force,
    )

    # drain 没成功：默认不 delete（除非 force）
    if not r2.get("ok") and not force:
        return {
            "ok": False,
            "steps": [r1, r2],
            "hint": "drain not clean; set force=true to delete anyway",
        }

    r3 = delete_node(node_name)

    ok = all(s.get("ok") is True for s in [r1, r2, r3])
    return {
        "ok": ok,
        "steps": [r1, r2, r3],
        "node_side_hint": [
            "若要彻底退役该机器，请到该节点上停止/卸载 k3s-agent，否则可能自动重新注册",
            "常见卸载脚本：/usr/local/bin/k3s-agent-uninstall.sh",
        ],
    }

