# routers/ops.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from services.ops.heal_reset import reset_heal_state
from services.ops.schemas import HealResetReq, HealResetResp
from services.ops.audit import list_events, delete_event_by_id, list_actions, delete_action_by_id
from services.ops.healer import run_heal_scan_once
from services.ops.scheduler import get_status
from services.ops.heal_view import list_heal_deployments, get_heal_deployment_detail
from services.alert_client import list_alerts
from services.ops.runtime_config import get_heal_decay_config, set_heal_decay_config

router = APIRouter(prefix="/api/ops", tags=["Ops"])


# -------------------- heal events --------------------
@router.get("/heal/events")
def heal_events(limit: int = 50, offset: int = 0):
    return {"items": list_events(limit=limit, offset=offset)}


@router.delete("/heal/events/{event_id}")
def heal_event_delete(event_id: int):
    try:
        ok = delete_event_by_id(event_id)
        if not ok:
            raise HTTPException(status_code=404, detail="event not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete event failed: {e}")


# -------------------- heal run/reset/status --------------------
@router.post("/heal/run")
def heal_run_once(namespace: Optional[str] = None):
    try:
        result = run_heal_scan_once(namespace=namespace)
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"heal run failed: {e}")


@router.get("/heal/status")
def heal_status():
    # 你原来就是直接 return get_status()（:contentReference[oaicite:6]{index=6}）
    return get_status()

@router.post("/heal/reset", response_model=HealResetResp)
def heal_reset(req: HealResetReq):
    out = reset_heal_state(
        namespace=req.namespace,
        deployment_uid=req.deployment_uid,
        deployment_name=req.deployment_name,
        restore_replicas=req.restore_replicas,
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("reason") or "reset failed")
    return HealResetResp(**out)


# -------------------- ✅ heal decay config (for UI buttons) --------------------
class HealDecayCfgResp(BaseModel):
    enabled: bool
    step: int


class HealDecayCfgReq(BaseModel):
    enabled: bool = Field(..., description="enable decay on recovered")
    step: int = Field(1, ge=1, le=10, description="decay step per recovered")


@router.get("/heal/decay", response_model=HealDecayCfgResp)
def heal_decay_get():
    enabled, step = get_heal_decay_config()
    return HealDecayCfgResp(enabled=enabled, step=step)


@router.put("/heal/decay", response_model=HealDecayCfgResp)
def heal_decay_set(req: HealDecayCfgReq):
    enabled, step = set_heal_decay_config(enabled=req.enabled, step=req.step)
    return HealDecayCfgResp(enabled=enabled, step=step)


# -------------------- actions audit --------------------
@router.get("/actions")
def actions(limit: int = 50, offset: int = 0):
    return {"items": list_actions(limit=limit, offset=offset)}


@router.delete("/actions/{action_id}")
def action_delete(action_id: int):
    try:
        ok = delete_action_by_id(action_id)
        if not ok:
            raise HTTPException(status_code=404, detail="action not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete action failed: {e}")


# -------------------- ✅ 阶段3.3：Deployment 维度聚合视图 --------------------
@router.get("/heal/deployments")
def heal_deployments(limit: int = 200, offset: int = 0, namespace: Optional[str] = None):
    """
    给前端 Tab 展示用：正常 / pending / 熔断中 + 最近一次自愈/失败次数
    """
    return {"items": list_heal_deployments(limit=limit, offset=offset, namespace=namespace)}


@router.get("/heal/deployments/{namespace}/{deployment_uid}")
def heal_deployment_detail(namespace: str, deployment_uid: str):
    d = get_heal_deployment_detail(namespace=namespace, deployment_uid=deployment_uid)
    if not d:
        raise HTTPException(status_code=404, detail="deployment not found")
    return d


# -------------------- ✅ 告警（Alertmanager 当前 alerts） --------------------
@router.get("/alerts")
def alerts():
    return {"items": list_alerts()}