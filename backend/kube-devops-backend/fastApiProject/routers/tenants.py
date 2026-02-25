# routers/tenants.py
from __future__ import annotations
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.tenants.service import (
    list_tenants, get_tenant, create_tenant, delete_tenant, toggle_tenant,
    bind_namespace, unbind_namespace, upsert_labels, update_quota,
    list_members, add_member, change_member_role, remove_member
)

TenantStatus = Literal["active", "disabled", "warning"]
MemberRole = Literal["viewer", "editor", "admin"]

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

class TenantCreateIn(BaseModel):
    name: str
    bindNamespace: Optional[str] = ""
    autoCreateNamespace: bool = True
    createAdminUser: bool = True
    adminUsername: Optional[str] = None
    pwdMode: Literal["auto", "manual"] = "auto"
    tempPassword: Optional[str] = None
    mustChangePassword: bool = True
    quotaCpu: str = "8"
    quotaMem: str = "16Gi"

@router.get("")
def api_list(keyword: Optional[str] = None, status: Optional[TenantStatus] = None):
    try:
        return {"items": list_tenants(keyword=keyword, status=status)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{tenant_id}")
def api_get(tenant_id: str):
    try:
        return {"tenant": get_tenant(tenant_id)}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("")
def api_create(payload: TenantCreateIn):
    try:
        return create_tenant(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{tenant_id}")
def api_delete(
    tenant_id: str,
    deleteNamespaces: bool = Query(True, description="危险：同时删除绑定的 K8s namespace"),
):
    try:
        delete_tenant(tenant_id, delete_namespaces=deleteNamespaces)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{tenant_id}/toggle")
def api_toggle(tenant_id: str):
    try:
        st = toggle_tenant(tenant_id)
        return {"ok": True, "status": st}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BindNsIn(BaseModel):
    namespace: str
    autoCreate: bool = True

@router.post("/{tenant_id}/namespaces")
def api_bind_ns(tenant_id: str, payload: BindNsIn):
    try:
        nss = bind_namespace(tenant_id, payload.namespace, auto_create=payload.autoCreate)
        return {"ok": True, "namespaces": nss}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{tenant_id}/namespaces/{namespace}")
def api_unbind_ns(tenant_id: str, namespace: str):
    try:
        nss = unbind_namespace(tenant_id, namespace)
        return {"ok": True, "namespaces": nss}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class LabelsIn(BaseModel):
    labels: dict[str, str] = Field(default_factory=dict)

@router.put("/{tenant_id}/labels")
def api_labels(tenant_id: str, payload: LabelsIn):
    try:
        labels = upsert_labels(tenant_id, payload.labels)
        return {"ok": True, "labels": labels}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class QuotaIn(BaseModel):
    cpu: str
    memory: str

@router.put("/{tenant_id}/quota")
def api_quota(tenant_id: str, payload: QuotaIn):
    try:
        quota = update_quota(tenant_id, payload.cpu, payload.memory)
        return {"ok": True, "quota": quota}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Members
@router.get("/{tenant_id}/members")
def api_members(tenant_id: str):
    try:
        return {"items": list_members(tenant_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AddMemberIn(BaseModel):
    username: str
    email: Optional[str] = None
    role: MemberRole = "viewer"
    pwdMode: Literal["auto", "manual"] = "auto"
    tempPassword: Optional[str] = None
    mustChange: bool = True

@router.post("/{tenant_id}/members")
def api_add_member(tenant_id: str, payload: AddMemberIn):
    try:
        out = add_member(tenant_id, payload.model_dump())
        resp = {"ok": True, "member": out["member"]}
        if out.get("oneTimePassword"):
            resp["oneTimePassword"] = out["oneTimePassword"]
        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ChangeRoleIn(BaseModel):
    role: MemberRole

@router.put("/{tenant_id}/members/{username}/role")
def api_change_role(tenant_id: str, username: str, payload: ChangeRoleIn):
    try:
        change_member_role(tenant_id, username, payload.role)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{tenant_id}/members/{username}")
def api_remove_member(tenant_id: str, username: str):
    try:
        remove_member(tenant_id, username)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))