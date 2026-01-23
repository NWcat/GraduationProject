# db/repo_ai_state.py
from __future__ import annotations

import time
from typing import Iterable

from db.sqlite import get_conn, q, write_with_retry


def upsert_state(*, user: str, row_key: str, status: str) -> None:
    def _op() -> None:
        conn = get_conn()
        try:
            now = int(time.time())
            q(
                conn,
                """
                INSERT INTO ai_suggestion_state(user, row_key, status, updated_ts)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(user, row_key) DO UPDATE SET
                    status=excluded.status,
                    updated_ts=excluded.updated_ts
                """,
                (user, row_key, status, now),
            )
            conn.commit()
        finally:
            conn.close()

    write_with_retry(_op)


def get_states(*, user: str, row_keys: Iterable[str]) -> dict[str, str]:
    keys = [str(k) for k in row_keys if str(k).strip()]
    if not keys:
        return {}

    conn = get_conn()
    try:
        placeholders = ",".join(["?"] * len(keys))
        cur = q(
            conn,
            f"""
            SELECT row_key, status
            FROM ai_suggestion_state
            WHERE user=? AND row_key IN ({placeholders})
            """,
            [user, *keys],
        )
        return {str(r["row_key"]): str(r["status"]) for r in cur.fetchall()}
    finally:
        conn.close()
