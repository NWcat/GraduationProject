# services/ops/actions.py
from __future__ import annotations

from typing import Any, Dict, Optional

from services.ops.audit import log_action
from services.ops.schemas import ApplyActionReq, ApplyActionResp
from services.ops.k8s_api import (
    scale_deployment,
    restart_deployment,
    delete_pod,
    get_deployment_replicas,
    # ✅ 新增：资源 patch（Deployment 级别）
    patch_deployment_resources,
)


def _pick_str(d: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _pick_num(d: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except Exception:
            continue
    return None


def _build_cpu_value_from_m(mcpu: Optional[float]) -> Optional[str]:
    if mcpu is None:
        return None
    try:
        m = int(round(float(mcpu)))
    except Exception:
        return None
    if m <= 0:
        return None
    return f"{m}m"


def _build_mem_value_from_mb(mb: Optional[float]) -> Optional[str]:
    if mb is None:
        return None
    try:
        m = int(round(float(mb)))
    except Exception:
        return None
    if m <= 0:
        return None
    return f"{m}Mi"


def apply_action(req: ApplyActionReq) -> ApplyActionResp:
    action = (req.action or "").upper()
    dry = bool(req.dry_run)

    ns = req.target.get("namespace", "default")
    name = req.target.get("name")  # deployment name for scale/restart/tune

    if action == "SCALE_DEPLOYMENT":
        if not name:
            raise ValueError("target.name (deployment) is required for SCALE_DEPLOYMENT")

        before = get_deployment_replicas(namespace=ns, name=name)

        # ✅ 优先 final replicas
        final_replicas = req.params.get("replicas")
        if final_replicas is None:
            delta = int(req.params.get("replicas_delta", 1))
            final_replicas = max(0, before + delta)

        final_replicas = int(final_replicas)

        if dry:
            detail = f"dry-run: scale deployment/{name} in {ns} from {before} to {final_replicas}"
        else:
            detail = scale_deployment(namespace=ns, name=name, replicas=final_replicas)

        data = {
            "namespace": ns,
            "name": name,
            "before_replicas": int(before),
            "after_replicas": int(final_replicas),
        }

        log_action(action=action, target=req.target, params=req.params, dry_run=dry, result="success", detail=detail)
        return ApplyActionResp(ok=True, action=action, dry_run=dry, detail=detail, data=data)

    if action in ("RESTART_DEPLOYMENT",):
        if not name:
            raise ValueError("target.name (deployment) is required for RESTART_DEPLOYMENT")

        if dry:
            detail = f"dry-run: rollout restart deployment/{name} in {ns}"
        else:
            detail = restart_deployment(namespace=ns, name=name)

        data = {"namespace": ns, "name": name}
        log_action(action=action, target=req.target, params=req.params, dry_run=dry, result="success", detail=detail)
        return ApplyActionResp(ok=True, action=action, dry_run=dry, detail=detail, data=data)

    if action in ("DELETE_POD",):
        pod = req.target.get("pod") or req.target.get("name")
        if not pod:
            raise ValueError("target.pod (or target.name) is required for DELETE_POD")

        if dry:
            detail = f"dry-run: delete pod/{pod} in {ns}"
        else:
            detail = delete_pod(namespace=ns, name=pod)

        data = {"namespace": ns, "pod": pod}
        log_action(action=action, target=req.target, params=req.params, dry_run=dry, result="success", detail=detail)
        return ApplyActionResp(ok=True, action=action, dry_run=dry, detail=detail, data=data)

    # ✅ 新增：调整 Deployment 资源（requests/limits）
    if action in ("TUNE_REQUESTS_LIMITS",):
        if not name:
            raise ValueError("target.name (deployment) is required for TUNE_REQUESTS_LIMITS")

        # 兼容 params 命名：cpu_request_m / cpu_limit_m / mem_request_mb / mem_limit_mb
        # 也兼容 cpu_request_mcpu / cpu_limit_mcpu / mem_request_mib / mem_limit_mib 等
        cpu_req_m = _pick_num(req.params, "cpu_request_m", "cpu_request_mcpu", "cpu_request")
        cpu_lim_m = _pick_num(req.params, "cpu_limit_m", "cpu_limit_mcpu", "cpu_limit")
        mem_req_mb = _pick_num(req.params, "mem_request_mb", "mem_request_mib", "mem_request")
        mem_lim_mb = _pick_num(req.params, "mem_limit_mb", "mem_limit_mib", "mem_limit")

        # 也允许直接传 K8s 资源字符串（如 "200m"/"256Mi"）
        cpu_req_s = _pick_str(req.params, "cpu_request_str", "cpu_request_value")
        cpu_lim_s = _pick_str(req.params, "cpu_limit_str", "cpu_limit_value")
        mem_req_s = _pick_str(req.params, "mem_request_str", "mem_request_value")
        mem_lim_s = _pick_str(req.params, "mem_limit_str", "mem_limit_value")

        # 统一成 k8s value（字符串）
        cpu_request = cpu_req_s or _build_cpu_value_from_m(cpu_req_m)
        cpu_limit = cpu_lim_s or _build_cpu_value_from_m(cpu_lim_m)
        mem_request = mem_req_s or _build_mem_value_from_mb(mem_req_mb)
        mem_limit = mem_lim_s or _build_mem_value_from_mb(mem_lim_mb)

        if not any([cpu_request, cpu_limit, mem_request, mem_limit]):
            raise ValueError(
                "params must include at least one of cpu_request/cpu_limit/mem_request/mem_limit "
                "(e.g. cpu_limit_m=200, mem_limit_mb=256)"
            )

        if dry:
            detail = (
                f"dry-run: patch deployment/{name} resources in {ns} "
                f"cpu_request={cpu_request} cpu_limit={cpu_limit} mem_request={mem_request} mem_limit={mem_limit}"
            )
            data = {
                "namespace": ns,
                "name": name,
                "cpu_request": cpu_request,
                "cpu_limit": cpu_limit,
                "mem_request": mem_request,
                "mem_limit": mem_limit,
            }
        else:
            detail, data = patch_deployment_resources(
                namespace=ns,
                name=name,
                cpu_request=cpu_request,
                cpu_limit=cpu_limit,
                mem_request=mem_request,
                mem_limit=mem_limit,
            )

        log_action(action=action, target=req.target, params=req.params, dry_run=dry, result="success", detail=detail)
        return ApplyActionResp(ok=True, action=action, dry_run=dry, detail=detail, data=data)

    detail = f"action not implemented: {action}"
    log_action(action=action, target=req.target, params=req.params, dry_run=dry, result="skipped", detail=detail)
    return ApplyActionResp(ok=False, action=action, dry_run=dry, detail=detail, data={})
