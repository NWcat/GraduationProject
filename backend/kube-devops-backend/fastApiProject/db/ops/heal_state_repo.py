from __future__ import annotations

import time
from typing import Any, Dict, Optional

from db.utils.sqlite import get_conn, q


def get_heal_snapshot(namespace: str, deployment_uid: str) -> Dict[str, Any]:
    ns = (namespace or "default").strip() or "default"
    duid = (deployment_uid or "").strip()
    now = int(time.time())
    if not duid:
        return {
            "exists": False,
            "namespace": ns,
            "deployment_uid": "",
            "status": "unknown",
            "fail_count": 0,
            "is_failing": 0,
            "pending": 0,
            "pending_until_ts": 0,
            "last_action": "",
            "last_reason": "",
            "last_pod": "",
            "last_ts": 0,
            "last_result": "",
        }

    conn = get_conn()
    try:
        srow = q(
            conn,
            """
            SELECT namespace, deployment_uid, deployment_name, fail_count, is_failing, reason, updated_ts
            FROM heal_state WHERE namespace=? AND deployment_uid=?
            """,
            (ns, duid),
        ).fetchone()
        prow = q(
            conn,
            """
            SELECT pending, pending_until_ts, deployment_name, last_action, last_action_ts,
                   last_pod, last_reason
            FROM heal_pending WHERE namespace=? AND deployment_uid=?
            """,
            (ns, duid),
        ).fetchone()
        erow = q(
            conn,
            """
            SELECT ts, action, reason, pod, result
            FROM heal_events WHERE namespace=? AND deployment_uid=?
            ORDER BY ts DESC LIMIT 1
            """,
            (ns, duid),
        ).fetchone()
    finally:
        conn.close()

    fail_count = int(srow["fail_count"] or 0) if srow else 0
    is_failing = int(srow["is_failing"] or 0) if srow else 0

    pending = int(prow["pending"] or 0) if prow else 0
    pending_until_ts = int(prow["pending_until_ts"] or 0) if prow else 0

    last_action = str((prow or {}).get("last_action") or (erow or {}).get("action") or "")
    last_reason = str((prow or {}).get("last_reason") or (erow or {}).get("reason") or "")
    last_pod = str((prow or {}).get("last_pod") or (erow or {}).get("pod") or "")
    last_ts = int((erow or {}).get("ts") or (prow or {}).get("last_action_ts") or 0)
    last_result = str((erow or {}).get("result") or "")

    if is_failing == 1:
        status = "circuit_open"
    elif pending == 1 and pending_until_ts > now:
        status = "pending"
    else:
        status = "normal" if srow or prow or erow else "unknown"

    return {
        "exists": bool(srow or prow or erow),
        "namespace": ns,
        "deployment_uid": duid,
        "status": status,
        "fail_count": fail_count,
        "is_failing": is_failing,
        "pending": pending,
        "pending_until_ts": pending_until_ts if status == "pending" else 0,
        "last_action": last_action,
        "last_reason": last_reason,
        "last_pod": last_pod,
        "last_ts": last_ts,
        "last_result": last_result,
    }
