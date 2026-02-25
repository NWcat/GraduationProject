# routers/clusters.py
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.clusters.service import (
    add_cluster,
    activate_cluster,
    delete_cluster,
    get_active_cluster,
    list_clusters,
    verify_cluster,
)

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


class AddClusterReq(BaseModel):
    name: str = Field(..., min_length=1)
    type: Literal["self-hosted", "managed"] = "managed"
    provider: str = ""
    kubeconfig: str = Field(..., min_length=1)


class VerifyClusterReq(BaseModel):
    kubeconfig: str = Field(..., min_length=1)


@router.get("")
def api_list_clusters():
    return list_clusters()


# ✅ 新增：当前 active 集群
@router.get("/active")
def api_get_active_cluster():
    return {"ok": True, "active": get_active_cluster()}


# ✅ 新增：只校验 kubeconfig（不入库）
@router.post("/verify")
def api_verify_cluster(req: VerifyClusterReq):
    return verify_cluster(req.kubeconfig)


@router.post("")
def api_add_cluster(req: AddClusterReq):
    return add_cluster(req.name, req.type, req.provider, req.kubeconfig)


@router.post("/{cluster_id}/activate")
def api_activate_cluster(cluster_id: int):
    return activate_cluster(cluster_id)


@router.delete("/{cluster_id}")
def api_delete_cluster(cluster_id: int):
    return delete_cluster(cluster_id)
