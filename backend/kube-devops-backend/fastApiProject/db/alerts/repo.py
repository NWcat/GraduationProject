from __future__ import annotations

import json
import time
import hashlib
from typing import Any, Dict, Iterable, List, Optional, Tuple

from db.utils.sqlite import get_conn, q, write_with_retry


def _stable_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def normalize_fingerprint(
    *,
    fingerprint: Optional[str],
    labels: Dict[str, Any],
) -> str:
    fp = str(fingerprint or "").strip()
    if fp:
        return fp
    return _stable_hash(labels or {})


def upsert_alert(
    *,
    fingerprint: str,
    status: str,
    labels: Dict[str, Any],
    annotations: Dict[str, Any],
    starts_at: str,
    ends_at: str,
    source: str,
) -> int:
    def _op() -> int:
        conn = get_conn()
        try:
            now = int(time.time())
            labels_json = json.dumps(labels or {}, ensure_ascii=True, sort_keys=True, default=str)
            annotations_json = json.dumps(annotations or {}, ensure_ascii=True, sort_keys=True, default=str)
            cur = q(
                conn,
                """
                INSERT INTO alerts(
                    fingerprint, status, labels_json, annotations_json,
                    starts_at, ends_at, last_seen, source, created_at,
                    last_push_status, last_push_error, last_push_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', 0)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    status=excluded.status,
                    labels_json=excluded.labels_json,
                    annotations_json=excluded.annotations_json,
                    starts_at=excluded.starts_at,
                    ends_at=excluded.ends_at,
                    last_seen=excluded.last_seen,
                    source=excluded.source
                """,
                (
                    str(fingerprint),
                    str(status or ""),
                    labels_json,
                    annotations_json,
                    str(starts_at or ""),
                    str(ends_at or ""),
                    now,
                    str(source or ""),
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()

    return int(write_with_retry(_op))


def update_push_status(
    *,
    fingerprint: str,
    status: str,
    error: str,
    pushed_at: Optional[int] = None,
) -> None:
    def _op() -> None:
        conn = get_conn()
        try:
            ts = int(pushed_at or time.time())
            q(
                conn,
                """
                UPDATE alerts
                SET last_push_status=?, last_push_error=?, last_push_at=?
                WHERE fingerprint=?
                """,
                (str(status or ""), str(error or ""), ts, str(fingerprint)),
            )
            conn.commit()
        finally:
            conn.close()

    write_with_retry(_op)


def list_alerts(
    *,
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    where = []
    params: List[Any] = []

    if status:
        where.append("status=?")
        params.append(str(status))
    if source:
        where.append("source=?")
        params.append(str(source))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_conn()
    try:
        cur = q(
            conn,
            f"""
            SELECT *
            FROM alerts
            {where_sql}
            ORDER BY last_seen DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        items = []
        for r in cur.fetchall():
            items.append(
                {
                    "id": int(r["id"]),
                    "fingerprint": str(r["fingerprint"]),
                    "status": str(r["status"]),
                    "labels": json.loads(r["labels_json"] or "{}"),
                    "annotations": json.loads(r["annotations_json"] or "{}"),
                    "starts_at": str(r["starts_at"]),
                    "ends_at": str(r["ends_at"]),
                    "last_seen": int(r["last_seen"]),
                    "source": str(r["source"]),
                    "created_at": int(r["created_at"]),
                    "last_push_status": str(r["last_push_status"]),
                    "last_push_error": str(r["last_push_error"]),
                    "last_push_at": int(r["last_push_at"]),
                }
            )
        return {"items": items, "limit": limit, "offset": offset}
    finally:
        conn.close()


def get_alert(alert_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT * FROM alerts WHERE id=?", (int(alert_id),))
        r = cur.fetchone()
        if not r:
            return None
        return {
            "id": int(r["id"]),
            "fingerprint": str(r["fingerprint"]),
            "status": str(r["status"]),
            "labels": json.loads(r["labels_json"] or "{}"),
            "annotations": json.loads(r["annotations_json"] or "{}"),
            "starts_at": str(r["starts_at"]),
            "ends_at": str(r["ends_at"]),
            "last_seen": int(r["last_seen"]),
            "source": str(r["source"]),
            "created_at": int(r["created_at"]),
            "last_push_status": str(r["last_push_status"]),
            "last_push_error": str(r["last_push_error"]),
            "last_push_at": int(r["last_push_at"]),
        }
    finally:
        conn.close()

