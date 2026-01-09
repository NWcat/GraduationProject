# routers/workloads.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.workloads_service import (
    list_namespaces,
    list_deployments,
    list_statefulsets,
    list_pods,
    get_resource_yaml,
    scale_workload,
    restart_workload,
    delete_pod,
    get_pod_logs,
    delete_workload,
)

# ✅ 新建/应用 YAML：kubectl apply -f -
# 如果你还没加这个文件：services/kubectl_runner.py，按我上次给你的创建
from services.kubectl_runner import kubectl_apply_yaml


Kind = Literal["deployment", "statefulset", "pod"]
RowStatus = Literal["running", "warning", "failed", "unknown"]

router = APIRouter(prefix="/api/workloads", tags=["workloads"])


# -----------------------------
# Response Models
# -----------------------------
class WorkloadRow(BaseModel):
    kind: Kind
    kindTag: Optional[str] = None
    name: str
    namespace: str
    status: RowStatus
    image: Optional[str] = None
    age: Optional[str] = None

    # Deploy/STS
    replicas: Optional[int] = None
    readyReplicas: Optional[int] = None
    strategy: Optional[str] = None
    updatedAt: Optional[str] = None

    # Pod
    node: Optional[str] = None
    podIP: Optional[str] = None
    restarts: Optional[int] = None
    createdAt: Optional[str] = None


class WorkloadsListResp(BaseModel):
    updatedAt: str
    items: list[WorkloadRow]


class OkResp(BaseModel):
    ok: bool = True


class YamlResp(BaseModel):
    yaml: str


class LogsResp(BaseModel):
    logs: str


class ApplyIn(BaseModel):
    yaml: str = Field(..., description="Kubernetes YAML，支持多文档（---）")


class ApplyOut(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""

class DeleteWorkloadIn(BaseModel):
    kind: Literal["deployment", "statefulset"]
    namespace: str
    name: str
    deletePVC: bool = False


class DeleteWorkloadOut(BaseModel):
    ok: bool
    message: str = ""

# -----------------------------
# Endpoints
# -----------------------------
@router.get("/namespaces", response_model=list[str])
def api_namespaces():
    try:
        return list_namespaces()
    except Exception as e:
        # 这里抛出 500，前端能收到明确错误
        raise HTTPException(status_code=500, detail=f"list_namespaces 失败：{e}")





@router.post("/delete", response_model=DeleteWorkloadOut)
def api_delete_workload(payload: DeleteWorkloadIn):
    try:
        delete_workload(
            kind=payload.kind,
            namespace=payload.namespace,
            name=payload.name,
            delete_pvc=payload.deletePVC,
        )
        return DeleteWorkloadOut(ok=True, message="deleted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete_workload 失败：{e}")


@router.get("", response_model=WorkloadsListResp)
def api_workloads(
    kind: Kind,
    namespace: Optional[str] = None,
    status: Optional[RowStatus] = None,
    keyword: Optional[str] = None,
):
    now = datetime.now(timezone.utc).isoformat()

    try:
        if kind == "deployment":
            items = list_deployments(namespace=namespace, status=status, keyword=keyword)
        elif kind == "statefulset":
            items = list_statefulsets(namespace=namespace, status=status, keyword=keyword)
        else:
            items = list_pods(namespace=namespace, status=status, keyword=keyword)
        return WorkloadsListResp(updatedAt=now, items=items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"list_workloads 失败：{e}")


@router.get("/yaml", response_model=YamlResp)
def api_yaml(kind: Kind, namespace: str, name: str):
    try:
        y = get_resource_yaml(kind=kind, namespace=namespace, name=name)
        return YamlResp(yaml=y)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"get_resource_yaml 失败：{e}")


class ScaleIn(BaseModel):
    kind: Literal["deployment", "statefulset"]
    namespace: str
    name: str
    replicas: int = Field(..., ge=0, le=200)


@router.post("/scale", response_model=OkResp)
def api_scale(payload: ScaleIn):
    try:
        scale_workload(
            kind=payload.kind,
            namespace=payload.namespace,
            name=payload.name,
            replicas=payload.replicas,
        )
        return OkResp(ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"scale_workload 失败：{e}")


class RestartIn(BaseModel):
    kind: Literal["deployment", "statefulset"]
    namespace: str
    name: str


@router.post("/restart", response_model=OkResp)
def api_restart(payload: RestartIn):
    try:
        restart_workload(kind=payload.kind, namespace=payload.namespace, name=payload.name)
        return OkResp(ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"restart_workload 失败：{e}")


# ✅ 删除 Pod：建议用 POST /pod/delete（最兼容前端，不受 DELETE body 限制）
class DeletePodIn(BaseModel):
    namespace: str
    name: str


@router.post("/pod/delete", response_model=OkResp)
def api_delete_pod(payload: DeletePodIn):
    try:
        delete_pod(namespace=payload.namespace, name=payload.name)
        return OkResp(ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete_pod 失败：{e}")


# （可选）也提供 RESTful 的 DELETE（用 query 参数，不用 body）
@router.delete("/pod", response_model=OkResp)
def api_delete_pod_rest(
    namespace: str = Query(..., description="namespace"),
    name: str = Query(..., description="pod name"),
):
    try:
        delete_pod(namespace=namespace, name=name)
        return OkResp(ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete_pod 失败：{e}")


@router.get("/pod/logs", response_model=LogsResp)
def api_pod_logs(
    namespace: str,
    name: str,
    container: Optional[str] = None,
    tailLines: int = 200,
):
    # 简单防呆：避免太大
    if tailLines < 1:
        tailLines = 200
    if tailLines > 2000:
        tailLines = 2000

    try:
        logs = get_pod_logs(
            namespace=namespace,
            name=name,
            container=container,
            tail_lines=tailLines,
        )
        return LogsResp(logs=logs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"get_pod_logs 失败：{e}")


# ✅ 新建/应用 YAML（你“新建”弹窗提交就打这个）
@router.post("/apply", response_model=ApplyOut)
def api_apply(payload: ApplyIn):
    text = (payload.yaml or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="yaml 不能为空")

    try:
        code, out, err = kubectl_apply_yaml(text)
        return ApplyOut(ok=(code == 0), stdout=out, stderr=err)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"kubectl apply 失败：{e}")
