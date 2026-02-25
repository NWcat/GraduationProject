from __future__ import annotations
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query, Depends, Body
import uuid
from typing import Any, Dict, List

from db.tasks.repo import list_tasks, get_task, create_task, delete_tasks_by_ids, delete_all_tasks
from routers.authz import require_user

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


class BatchDeleteReq(BaseModel):
    task_ids: List[str]


@router.get("/list", dependencies=[Depends(require_user)])
def tasks_list(
    status: str | None = Query(None),
    type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    result = list_tasks(status=status, type=type, limit=limit, offset=offset)
    return {
        "items": result.get("items", []),
        "limit": result.get("limit", limit),
        "offset": result.get("offset", offset),
    }


@router.get("/get", dependencies=[Depends(require_user)])
def task_get(task_id: str = Query(...)):
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task": task}


@router.post("/submit", dependencies=[Depends(require_user)])
def task_submit(req: Dict[str, Any] = Body(...)):
    task_type = str(req.get("type") or "").strip()
    payload = req.get("payload")
    if not task_type:
        raise HTTPException(status_code=400, detail="type required")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be object")
    task_id = uuid.uuid4().hex
    create_task(task_id=task_id, type=task_type, input_json=payload)
    return {"ok": True, "task_id": task_id, "status": "PENDING"}


@router.get("/{task_id}", dependencies=[Depends(require_user)])
def task_detail(task_id: str):
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task": task}


@router.delete("/{task_id}", dependencies=[Depends(require_user)])
def task_delete(task_id: str):
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")
    deleted_count = delete_tasks_by_ids([task_id])
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="task not found")
    return {"ok": True, "deleted_count": deleted_count}


@router.post("/batch-delete", dependencies=[Depends(require_user)])
def tasks_batch_delete(req: BatchDeleteReq):
    if not req.task_ids:
        return {"ok": True, "deleted_count": 0}
    deleted_count = delete_tasks_by_ids(req.task_ids)
    return {"ok": True, "deleted_count": deleted_count}


@router.delete("/all", dependencies=[Depends(require_user)])
def tasks_delete_all():
    deleted_count = delete_all_tasks()
    return {"ok": True, "deleted_count": deleted_count}