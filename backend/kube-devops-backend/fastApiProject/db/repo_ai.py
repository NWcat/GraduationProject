# db/repo_ai.py
from __future__ import annotations

import time
from typing import Any

from db.sqlite import get_conn, q, write_with_retry


def insert_feedback(
    *,
    ts: int,
    target: str,
    key: str,
    suggestion_id: str,
    action_kind: str,
    outcome: str,
    detail: str,
) -> int:
    def _op() -> int:
        conn = get_conn()
        try:
            cur = q(
                conn,
                """
                INSERT INTO ai_feedback(ts, target, key, suggestion_id, action_kind, outcome, detail)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (int(ts), target, key, suggestion_id, action_kind, outcome, detail),
            )
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()

    return int(write_with_retry(_op))


def upsert_evolution(
    *,
    target: str,
    key: str,
    observe_ratio: float,
    trigger_ratio: float,
    sustain_minutes: int,
) -> None:
    def _op() -> None:
        conn = get_conn()
        try:
            now = int(time.time())
            q(
                conn,
                """
                INSERT INTO ai_evolution(target, key, observe_ratio, trigger_ratio, sustain_minutes, updated_ts)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(target, key) DO UPDATE SET
                    observe_ratio=excluded.observe_ratio,
                    trigger_ratio=excluded.trigger_ratio,
                    sustain_minutes=excluded.sustain_minutes,
                    updated_ts=excluded.updated_ts
                """,
                (target, key, float(observe_ratio), float(trigger_ratio), int(sustain_minutes), now),
            )
            conn.commit()
        finally:
            conn.close()

    write_with_retry(_op)


def delete_evolution(*, target: str, key: str) -> bool:
    def _op() -> bool:
        conn = get_conn()
        try:
            cur = q(conn, "DELETE FROM ai_evolution WHERE target=? AND key=?", (target, key))
            conn.commit()
            return (cur.rowcount or 0) > 0
        finally:
            conn.close()

    return bool(write_with_retry(_op))
