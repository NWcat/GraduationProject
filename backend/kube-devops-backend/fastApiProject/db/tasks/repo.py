from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from db.utils.sqlite import get_conn, q, write_with_retry


def create_task(*, task_id: str, type: str, input_json: Any = None) -> Dict[str, Any]:
    def _op() -> Dict[str, Any]:
        conn = get_conn()
        try:
            now = int(time.time())
            payload_json = ""
            if input_json is not None:
                try:
                    # ✅ 处理 Pydantic 模型：转换为字典
                    processed_input = input_json
                    if hasattr(processed_input, 'model_dump'):
                        processed_input = processed_input.model_dump()
                    elif hasattr(processed_input, 'dict'):
                        processed_input = processed_input.dict()
                    payload_json = json.dumps(processed_input, ensure_ascii=False, default=str)
                except Exception:
                    payload_json = json.dumps({"_raw": str(input_json)}, ensure_ascii=False)
            q(
                conn,
                """
                INSERT INTO tasks(
                    task_id, type, status, progress, input_json, result_json, error,
                    attempts, started_at, finished_at, worker_id, created_at, updated_at
                )
                VALUES(?, ?, 'PENDING', 0, ?, '', '', 0, 0, 0, '', ?, ?)
                """,
                (str(task_id), str(type), payload_json, now, now),
            )
            conn.commit()
            return {
                "task_id": str(task_id),
                "type": str(type),
                "status": "PENDING",
                "progress": 0.0,
                "input_json": payload_json,
                "result_json": "",
                "error": "",
                "attempts": 0,
                "started_at": 0,
                "finished_at": 0,
                "worker_id": "",
                "created_at": now,
                "updated_at": now,
            }
        finally:
            conn.close()

    return write_with_retry(_op)


def update_task_status(
    *,
    task_id: str,
    status: str,
    progress: Optional[float] = None,
    result: Optional[Any] = None,
    error: Optional[str] = None,
) -> None:
    def _op() -> None:
        conn = get_conn()
        try:
            now = int(time.time())
            result_json = ""
            if result is not None:
                try:
                    # ✅ 处理 Pydantic 模型：转换为字典
                    processed_result = result
                    if hasattr(processed_result, 'model_dump'):
                        processed_result = processed_result.model_dump()
                    elif hasattr(processed_result, 'dict'):
                        processed_result = processed_result.dict()
                    result_json = json.dumps(processed_result, ensure_ascii=False, default=str)
                except Exception:
                    result_json = json.dumps({"_raw": str(result)}, ensure_ascii=False)
            finished_at = now if str(status) in ("SUCCESS", "FAILED") else None
            q(
                conn,
                """
                UPDATE tasks
                SET status=?, progress=COALESCE(?, progress), result_json=?, error=?,
                    updated_at=?, finished_at=COALESCE(?, finished_at)
                WHERE task_id=?
                """,
                (
                    str(status),
                    float(progress) if progress is not None else None,
                    result_json,
                    str(error or ""),
                    now,
                    finished_at,
                    str(task_id),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    write_with_retry(_op)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT * FROM tasks WHERE task_id=?", (str(task_id),))
        row = cur.fetchone()
        if not row:
            return None
        result = None
        if row["result_json"]:
            try:
                result = json.loads(row["result_json"])
            except Exception:
                result = None
        input_obj = None
        input_json = str(row["input_json"] or "")
        if input_json:
            try:
                input_obj = json.loads(input_json)
            except Exception:
                input_obj = None
        return {
            "task_id": str(row["task_id"]),
            "type": str(row["type"]),
            "status": str(row["status"]),
            "progress": float(row["progress"] or 0.0),
            "input": input_obj,
            "input_json": input_json,
            "result_json": str(row["result_json"] or ""),
            "result": result,
            "error": str(row["error"] or ""),
            "attempts": int(row["attempts"] or 0),
            "started_at": int(row["started_at"] or 0),
            "finished_at": int(row["finished_at"] or 0),
            "worker_id": str(row["worker_id"] or ""),
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
        }
    finally:
        conn.close()


def list_tasks(
    *,
    status: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    where: List[str] = []
    params: List[Any] = []

    if status:
        where.append("status=?")
        params.append(str(status))
    if type:
        where.append("type=?")
        params.append(str(type))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_conn()
    try:
        cur = q(
            conn,
            f"""
            SELECT * FROM tasks
            {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        items = []
        for row in cur.fetchall():
            items.append(
                {
                    "task_id": str(row["task_id"]),
                    "type": str(row["type"]),
                    "status": str(row["status"]),
                    "progress": float(row["progress"] or 0.0),
                    "error": str(row["error"] or ""),
                    "created_at": int(row["created_at"]),
                    "updated_at": int(row["updated_at"]),
                }
            )
        return {"items": items, "limit": limit, "offset": offset}
    finally:
        conn.close()


def mark_pending_unknown() -> int:
    def _op() -> int:
        conn = get_conn()
        try:
            now = int(time.time())
            cur = q(
                conn,
                """
                UPDATE tasks
                SET status='UNKNOWN', updated_at=?
                WHERE status IN ('PENDING', 'RUNNING')
                """,
                (now,),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    return int(write_with_retry(_op))


def reset_running_tasks() -> int:
    def _op() -> int:
        conn = get_conn()
        try:
            now = int(time.time())
            cur = q(
                conn,
                """
                UPDATE tasks
                SET status='PENDING', started_at=0, updated_at=?, worker_id=''
                WHERE status='RUNNING'
                """,
                (now,),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    return int(write_with_retry(_op))


def claim_next_task(worker_id: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        cur = q(
            conn,
            """
            SELECT * FROM tasks
            WHERE status='PENDING'
            ORDER BY created_at ASC
            LIMIT 1
            """,
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return None
        now = int(time.time())
        cur = q(
            conn,
            """
            UPDATE tasks
            SET status='RUNNING', started_at=?, updated_at=?, worker_id=?, attempts=attempts+1
            WHERE task_id=? AND status='PENDING'
            """,
            (now, now, str(worker_id), str(row["task_id"])),
        )
        conn.commit()
        if int(cur.rowcount or 0) != 1:
            return None
        return {
            "task_id": str(row["task_id"]),
            "type": str(row["type"]),
            "status": "RUNNING",
            "input_json": str(row["input_json"] or ""),
            "attempts": int(row["attempts"] or 0) + 1,
        }
    finally:
        conn.close()


def delete_tasks_by_ids(task_ids: List[str]) -> int:
    if not task_ids:
        return 0
    
    placeholders = ','.join('?' for _ in task_ids)
    
    def _op() -> int:
        conn = get_conn()
        try:
            cur = q(
                conn,
                f"DELETE FROM tasks WHERE task_id IN ({placeholders})",
                task_ids,
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    return write_with_retry(_op)


def delete_all_tasks() -> int:
    def _op() -> int:
        conn = get_conn()
        try:
            cur = q(conn, "DELETE FROM tasks")
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    return write_with_retry(_op)