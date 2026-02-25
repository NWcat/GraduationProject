from __future__ import annotations

import json
from typing import Any, Dict, Optional

from db.utils.sqlite import get_conn, q


def _parse_params(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def get_last_ai_action(
    *,
    object_key: str,
    action_type: str,
) -> Optional[Dict[str, Any]]:
    if not object_key or not action_type:
        return None

    conn = get_conn()
    try:
        cur = q(
            conn,
            """
            SELECT ts, action, params, dry_run, result, detail
            FROM ops_actions
            WHERE dry_run=0
              AND params LIKE '%"ai_object_key"%'
              AND params LIKE '%"ai_action_type"%'
            ORDER BY ts DESC LIMIT 200
            """,
            (),
        )
        rows = cur.fetchall()
        for row in rows:
            params = _parse_params(str(row["params"] or ""))
            if params.get("ai_source") != "ai_execute":
                continue
            if params.get("ai_object_key") != object_key:
                continue
            if params.get("ai_action_type") != action_type:
                continue
            return {
                "ts": int(row["ts"] or 0),
                "action": str(row["action"] or ""),
                "params": params,
                "dry_run": int(row["dry_run"] or 0),
                "result": str(row["result"] or ""),
                "detail": str(row["detail"] or ""),
            }
        return None
    finally:
        conn.close()


def get_last_ai_action_ts(
    *,
    object_key: str,
    action_type: str,
) -> Optional[int]:
    row = get_last_ai_action(object_key=object_key, action_type=action_type)
    if not row:
        return None
    return int(row.get("ts") or 0)


def count_ai_actions_since(*, ts_start: int) -> int:
    ts_start = int(ts_start or 0)
    conn = get_conn()
    try:
        cur = q(
            conn,
            """
            SELECT params
            FROM ops_actions
            WHERE dry_run=0
              AND ts >= ?
              AND params LIKE '%"ai_source"%'
            """,
            (ts_start,),
        )
        rows = cur.fetchall()
        count = 0
        for row in rows:
            params = _parse_params(str(row["params"] or ""))
            if params.get("ai_source") == "ai_execute":
                count += 1
        return int(count)
    finally:
        conn.close()
