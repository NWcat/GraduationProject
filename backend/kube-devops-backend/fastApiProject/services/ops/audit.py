# services/ops/audit.py
from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from db.sqlite import get_conn, q

MAX_FAILURE_COUNT = 3  # 保留也行（仅用于展示/外部代码需要），但 log_heal_event 不再用它推进状态


def log_action(
    action: str,
    target: Dict[str, Any],
    params: Dict[str, Any],
    dry_run: bool,
    result: str,
    detail: str,
):
    conn = get_conn()
    try:
        q(
            conn,
            "INSERT INTO ops_actions(ts, action, target, params, dry_run, result, detail) VALUES(?,?,?,?,?,?,?)",
            (
                int(time.time()),
                action,
                json.dumps(target, ensure_ascii=False, default=str),
                json.dumps(params, ensure_ascii=False, default=str),
                1 if dry_run else 0,
                result,
                detail,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_events(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT * FROM heal_events ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_actions(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT * FROM ops_actions ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_event_by_id(event_id: int) -> bool:
    conn = get_conn()
    try:
        cur = q(conn, "DELETE FROM heal_events WHERE id=?", (int(event_id),))
        conn.commit()
        return (cur.rowcount or 0) > 0
    finally:
        conn.close()


def delete_action_by_id(action_id: int) -> bool:
    conn = get_conn()
    try:
        cur = q(conn, "DELETE FROM ops_actions WHERE id=?", (int(action_id),))
        conn.commit()
        return (cur.rowcount or 0) > 0
    finally:
        conn.close()


def log_heal_event(
    *,
    namespace: str,
    deployment_uid: str,      # ✅ 逻辑聚合键（必须）
    deployment_name: str,     # ✅ 仅展示
    pod: str,
    pod_uid: str,
    reason: str,
    action: str,
    result: str,
    fail_count_inc: int = 0,  # ✅ 仍保留字段，但它只影响 heal_events.fail_count（审计统计），不再影响 heal_state
) -> Dict[str, Any]:
    """
    ✅ 纯审计：只写 heal_events（给 UI/排查看）
    ❌ 不再同步/推进 heal_state（状态机由 healer.py 维护，且 is_failing 只由 scale_ok 决定）
    """
    key_uid = (deployment_uid or "").strip()
    if not key_uid:
        return {"ok": False, "skipped": True, "reason": "empty_deployment_uid"}

    show_name = (deployment_name or "unknown").strip() or "unknown"
    inc = int(fail_count_inc or 0)
    if inc < 0:
        inc = 0

    now_ts = int(time.time())

    conn = get_conn()
    try:
        cur = q(
            conn,
            "SELECT id, fail_count, is_failing FROM heal_events WHERE namespace=? AND deployment_uid=?",
            (namespace, key_uid),
        )
        row = cur.fetchone()

        if row:
            new_fail = int(row["fail_count"] or 0) + inc

            # ✅ 注意：这里的 is_failing 只是“事件表历史字段”，不作为真相。
            # 既然按 A 真相在 heal_state，我们这里不主动改 is_failing，避免语义混乱。
            q(
                conn,
                """
                UPDATE heal_events
                SET ts=?, deployment_name=?, pod=?, pod_uid=?, reason=?, action=?, result=?, fail_count=?
                WHERE id=?
                """,
                (now_ts, show_name, pod, pod_uid, reason, action, result, int(new_fail), int(row["id"])),
            )

            conn.commit()
            return {
                "ok": True,
                "id": int(row["id"]),
                "fail_count": int(new_fail),
                "is_failing": int(row["is_failing"] or 0),
            }

        # insert new row
        q(
            conn,
            """
            INSERT INTO heal_events
              (ts, namespace, deployment_uid, deployment_name, pod, pod_uid, reason, action, result, fail_count, is_failing)
            VALUES (?,  ?,        ?,             ?,              ?,   ?,      ?,      ?,      ?,      ?,         ?)
            """,
            (
                now_ts,
                namespace,
                key_uid,
                show_name,
                pod,
                pod_uid,
                reason,
                action,
                result,
                int(inc),
                0,  # ✅ 按 A：事件表的 is_failing 不作为真相，默认 0（或保留原逻辑也行，但会误导）
            ),
        )

        conn.commit()

        cur2 = q(
            conn,
            "SELECT id, fail_count, is_failing FROM heal_events WHERE namespace=? AND deployment_uid=?",
            (namespace, key_uid),
        )
        r2 = cur2.fetchone()
        return {
            "ok": True,
            "id": int(r2["id"]),
            "fail_count": int(r2["fail_count"]),
            "is_failing": int(r2["is_failing"] or 0),
        }
    finally:
        conn.close()
