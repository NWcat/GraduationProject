# routers/namespaces.py
from __future__ import annotations

from typing import Dict, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.namespaces import service as svc

router = APIRouter(prefix="/api/namespaces", tags=["Namespaces"])

class NamespaceCreateIn(BaseModel):
    name: str
    labels: Dict[str, str] = {}
    managed: bool = True
    managedByTenantId: Optional[str] = None

class NamespaceLabelsPatchIn(BaseModel):
    labels: Dict[str, str] = {}

@router.get("")
def get_namespaces(keyword: Optional[str] = Query(default=None)):
    return {"items": svc.list_namespaces(keyword=keyword)}

@router.get("/options")
def get_namespace_options():
    return {"items": svc.list_namespace_options()}

@router.post("")
def post_namespace(body: NamespaceCreateIn):
    item = svc.create_namespace(
        name=body.name,
        labels=body.labels,
        managed=body.managed,
        managed_by_tenant_id=body.managedByTenantId,
    )
    return {"item": item}

@router.patch("/{name}/labels")
def patch_ns_labels(name: str, body: NamespaceLabelsPatchIn):
    item = svc.patch_namespace_labels(name=name, labels=body.labels)
    return {"item": item}

@router.delete("/{name}")
def delete_ns(name: str, purge_registry: bool = True):
    return svc.delete_namespace(name=name, purge_registry=purge_registry)
