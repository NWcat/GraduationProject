from __future__ import annotations

import time
from typing import Dict, Any

from config import settings
from db.utils.sqlite import get_conn, q
from db.tasks.repo import mark_pending_unknown
from services.ops.runtime_config import get_value


def _cfg_int(key: str, default: int) -> int:
    v, _src = get_value(key)
    try:
        return int(v)
    except Exception:
        return int(default)


def _log(action: str, detail: str) -> None:
    conn = get_conn()
    try:
        now = int(time.time())
        q(
            conn,
            "INSERT INTO maintenance_logs(ts, action, detail) VALUES(?, ?, ?)",
            (now, str(action), str(detail)),
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_by_ttl_days(days: int) -> Dict[str, Any]:
    days = max(1, int(days))
    cutoff = int(time.time()) - days * 86400
    out: Dict[str, Any] = {"days": days, "cutoff": cutoff, "deleted": {}}

    conn = get_conn()
    try:
        cur = q(conn, "DELETE FROM alerts WHERE last_seen < ?", (cutoff,))
        out["deleted"]["alerts"] = int(cur.rowcount or 0)
        cur = q(conn, "DELETE FROM tasks WHERE updated_at < ?", (cutoff,))
        out["deleted"]["tasks"] = int(cur.rowcount or 0)
        cur = q(conn, "DELETE FROM heal_events WHERE ts < ?", (cutoff,))
        out["deleted"]["heal_events"] = int(cur.rowcount or 0)
        conn.commit()
    finally:
        conn.close()

    _log("cleanup_ttl", str(out))
    return out


def run_startup_maintenance() -> Dict[str, Any]:
    ttl_days = _cfg_int("DATA_TTL_DAYS", int(getattr(settings, "DATA_TTL_DAYS", 7)))
    unknown_cnt = mark_pending_unknown()
    cleanup_out = cleanup_by_ttl_days(ttl_days)
    _log("tasks_unknown", f"marked_unknown={unknown_cnt}")
    return {"tasks_unknown": unknown_cnt, "cleanup": cleanup_out}

