from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Dict, Optional

from db.tasks.repo import claim_next_task, reset_running_tasks, update_task_status
from fastapi import HTTPException

_worker_started = False
_worker_lock = threading.Lock()


def _parse_payload(input_json: str) -> Dict[str, Any]:
    if not input_json:
        return {}
    try:
        payload = json.loads(input_json)
        return payload if isinstance(payload, dict) else {"_raw": payload}
    except Exception:
        return {"_raw": input_json}


def _dispatch_task(task_type: str, payload: Dict[str, Any]) -> Any:
    if task_type == "ai_forecast":
        from routers.ai import run_forecast_task

        return run_forecast_task(payload)
    if task_type == "ai_suggestions":
        from routers.ai import run_suggestions_task

        return run_suggestions_task(payload)
    if task_type == "ai_execute":
        from routers.ai import run_execute_task

        return run_execute_task(payload)
    raise ValueError(f"unsupported task type: {task_type}")


def _worker_loop(worker_id: str) -> None:
    reclaimed = reset_running_tasks()
    if reclaimed:
        print(f"tasks_worker reclaimed={reclaimed}")

    while True:
        task = claim_next_task(worker_id)
        if not task:
            time.sleep(0.8)
            continue
        task_id = str(task.get("task_id") or "")
        task_type = str(task.get("type") or "")
        payload = _parse_payload(str(task.get("input_json") or ""))
        print(f"tasks_worker claimed task_id={task_id} type={task_type}")
        try:
            result = _dispatch_task(task_type, payload)
            if isinstance(result, dict) and result.get("forbid"):
                reason = result.get("forbid_reason") or result.get("detail") or "操作被禁止"
                update_task_status(task_id=task_id, status="RESTRICTED", progress=1.0, result=result, error=str(reason))
                print(f"tasks_worker done task_id={task_id} status=RESTRICTED error={reason}")
            else:
                update_task_status(task_id=task_id, status="SUCCESS", progress=1.0, result=result, error=None)
                print(f"tasks_worker done task_id={task_id} status=SUCCESS")
        except HTTPException as e:
            update_task_status(
                task_id=task_id,
                status="FAILED",
                progress=1.0,
                result=None,
                error=str(getattr(e, "detail", "") or e),
            )
            print(f"tasks_worker done task_id={task_id} status=FAILED error={e}")
        except Exception as e:
            update_task_status(task_id=task_id, status="FAILED", progress=1.0, result=None, error=str(e))
            print(f"tasks_worker done task_id={task_id} status=FAILED error={e}")


def start_task_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
    worker_id = uuid.uuid4().hex[:8]
    t = threading.Thread(target=_worker_loop, args=(worker_id,), name="tasks-worker", daemon=True)
    t.start()
