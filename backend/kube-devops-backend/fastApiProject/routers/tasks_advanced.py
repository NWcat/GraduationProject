# 高级任务管理 API 端点实现
# 文件位置：routers/tasks_advanced.py

from fastapi import APIRouter, Query, HTTPException, status, Body
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import json
from db.tasks.repo import (
    get_task, list_tasks, update_task_status, delete_tasks_by_ids, delete_all_tasks
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class BatchDeleteReq(BaseModel):
    task_ids: List[str]


@router.post("/{task_id}/cancel", response_model=Dict[str, Any])
async def cancel_task_endpoint(
    task_id: str,
) -> Dict[str, Any]:
    """
    取消指定任务。

    - 仅 PENDING 或 RUNNING 状态的任务可被取消
    - 取消后状态变为 CANCELLED
    """
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status_val = task.get("status", "")
    if status_val == "CANCELLED":
        raise HTTPException(
            status_code=400,
            detail="Task already cancelled"
        )

    if status_val not in ("PENDING", "RUNNING"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task in {status_val} status"
        )

    # 更新任务状态
    update_task_status(
        task_id=task_id,
        status="CANCELLED",
        error="Task cancelled by user"
    )

    return {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": task_id,
            "status": "CANCELLED",
        }
    }


@router.post("/{task_id}/pause", response_model=Dict[str, Any])
async def pause_task_endpoint(
    task_id: str,
) -> Dict[str, Any]:
    """
    暂停指定任务。

    - 仅 RUNNING 状态的任务可被暂停
    - 暂停后状态为 PAUSED
    """
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status_val = task.get("status", "")
    if status_val == "PAUSED":
        raise HTTPException(
            status_code=400,
            detail="Task already paused"
        )

    if status_val != "RUNNING":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause task in {status_val} status"
        )

    update_task_status(task_id=task_id, status="PAUSED")

    return {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": task_id,
            "status": "PAUSED",
        }
    }


@router.post("/{task_id}/resume", response_model=Dict[str, Any])
async def resume_task_endpoint(
    task_id: str,
) -> Dict[str, Any]:
    """
    恢复被暂停的任务。

    - 仅 PAUSED 状态的任务可被恢复
    - 恢复后状态变为 PENDING（重新进入队列）
    """
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status_val = task.get("status", "")
    if status_val != "PAUSED":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume task in {status_val} status"
        )

    # 恢复任务（重新进入队列）
    update_task_status(task_id=task_id, status="PENDING")

    return {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": task_id,
            "status": "PENDING",
        }
    }


@router.delete("/{task_id}", response_model=Dict[str, Any])
async def delete_task_endpoint(
    task_id: str,
    force: bool = Query(False, description="Force delete running tasks")
) -> Dict[str, Any]:
    """
    删除任务记录。

    - 仅 SUCCESS, FAILED, CANCELLED, UNKNOWN 状态的任务可被删除
    - 如果设置 force=true，则可强制删除 RUNNING 任务
    """
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status_val = task.get("status", "")
    if status_val in ("RUNNING", "PENDING"):
        if not force:
            raise HTTPException(
                status_code=409,
                detail=f"Task is in {status_val} status. Set force=true to force delete."
            )
    
    deleted_count = delete_tasks_by_ids([task_id])
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found during deletion")


    return {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": task_id,
            "deleted": True,
            "deleted_count": deleted_count
        }
    }


@router.post("/batch-delete", response_model=Dict[str, Any])
async def tasks_batch_delete(req: BatchDeleteReq) -> Dict[str, Any]:
    """
    批量删除任务记录
    """
    if not req.task_ids:
        return {"code": 0, "message": "success", "data": {"deleted_count": 0}}
    
    # 可以在这里添加逻辑，检查是否有正在运行的任务
    
    deleted_count = delete_tasks_by_ids(req.task_ids)
    return {"code": 0, "message": "success", "data": {"deleted_count": deleted_count}}


@router.delete("/all", response_model=Dict[str, Any])
async def tasks_delete_all() -> Dict[str, Any]:
    """
    删除所有任务记录
    """
    deleted_count = delete_all_tasks()
    return {"code": 0, "message": "success", "data": {"deleted_count": deleted_count}}


@router.get("/stats", response_model=Dict[str, Any])
async def get_task_stats_endpoint(
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    days: int = Query(7, ge=1, le=90, description="Stats for last N days")
) -> Dict[str, Any]:
    """
    获取任务统计信息。

    返回：
    - 总任务数、成功数、失败数等
    - 按类型分类统计
    - 按日期分类统计
    """
    from db.utils.sqlite import get_conn, q

    conn = get_conn()
    since_ts = int((datetime.now() - timedelta(days=days)).timestamp())

    # 基础统计
    if task_type:
        stats_sql = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled,
                SUM(CASE WHEN status = 'PAUSED' THEN 1 ELSE 0 END) as paused,
                AVG(CASE WHEN finished_at > 0 THEN finished_at - started_at ELSE 0 END) as avg_duration
            FROM tasks
            WHERE created_at >= ? AND type = ?
        """
        cur = q(conn, stats_sql, (since_ts, task_type))
    else:
        stats_sql = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled,
                SUM(CASE WHEN status = 'PAUSED' THEN 1 ELSE 0 END) as paused,
                AVG(CASE WHEN finished_at > 0 THEN finished_at - started_at ELSE 0 END) as avg_duration
            FROM tasks
            WHERE created_at >= ?
        """
        cur = q(conn, stats_sql, (since_ts,))

    row = cur.fetchone()
    row_dict = dict(row) if row else {}

    total = row_dict.get("total", 0) or 0
    success = row_dict.get("success", 0) or 0
    success_rate = success / total if total > 0 else 0

    # 按类型统计
    by_type_sql = """
        SELECT type,
               COUNT(*) as total,
               SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success,
               SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
        FROM tasks
        WHERE created_at >= ?
        GROUP BY type
    """
    cur = q(conn, by_type_sql, (since_ts,))
    by_type = {}
    for row in cur.fetchall():
        row_dict = dict(row)
        by_type[row_dict["type"]] = {
            "total": row_dict.get("total", 0) or 0,
            "success": row_dict.get("success", 0) or 0,
            "failed": row_dict.get("failed", 0) or 0
        }

    # 按日期统计
    by_day_sql = """
        SELECT
            datetime(created_at, 'unixepoch') as day,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
        FROM tasks
        WHERE created_at >= ?
        GROUP BY date(created_at, 'unixepoch')
        ORDER BY day DESC
    """
    cur = q(conn, by_day_sql, (since_ts,))
    by_day = []
    for row in cur.fetchall():
        row_dict = dict(row)
        by_day.append({
            "day": row_dict.get("day", "")[:10],
            "total": row_dict.get("total", 0) or 0,
            "success": row_dict.get("success", 0) or 0,
            "failed": row_dict.get("failed", 0) or 0
        })

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": total,
            "success": success,
            "failed": row_dict.get("failed", 0) or 0,
            "cancelled": row_dict.get("cancelled", 0) or 0,
            "paused": row_dict.get("paused", 0) or 0,
            "success_rate": round(success_rate, 4),
            "avg_duration": int(row_dict.get("avg_duration", 0) or 0),
            "by_type": by_type,
            "by_day": by_day
        }
    }


@router.get("/history", response_model=Dict[str, Any])
async def get_task_history_endpoint(
    days: int = Query(7, ge=1, le=90),
    task_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    """
    获取任务执行历史时间线。
    """
    from db.utils.sqlite import get_conn, q

    conn = get_conn()
    since_ts = int((datetime.now() - timedelta(days=days)).timestamp())

    if task_type:
        sql = """
            SELECT task_id, type, status, created_at, updated_at, started_at, finished_at
            FROM tasks
            WHERE created_at >= ? AND type = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """
        cur = q(conn, sql, (since_ts, task_type, limit))
    else:
        sql = """
            SELECT task_id, type, status, created_at, updated_at, started_at, finished_at
            FROM tasks
            WHERE created_at >= ?
            ORDER BY updated_at DESC
            LIMIT ?
        """
        cur = q(conn, sql, (since_ts, limit))

    timeline = []
    for row in cur.fetchall():
        row_dict = dict(row)
        # 任务创建事件
        timeline.append({
            "timestamp": row_dict.get("created_at", 0),
            "event": "task_created",
            "task_id": row_dict.get("task_id", ""),
            "status": "PENDING"
        })
        # 任务开始事件
        if row_dict.get("started_at", 0) > 0:
            timeline.append({
                "timestamp": row_dict.get("started_at", 0),
                "event": "task_started",
                "task_id": row_dict.get("task_id", ""),
                "status": "RUNNING"
            })
        # 任务完成事件
        if row_dict.get("finished_at", 0) > 0:
            timeline.append({
                "timestamp": row_dict.get("finished_at", 0),
                "event": "task_completed",
                "task_id": row_dict.get("task_id", ""),
                "status": row_dict.get("status", "")
            })

    # 按时间戳排序
    timeline.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "timeline": timeline[:limit]
        }
    }