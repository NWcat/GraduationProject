# services/ops/heal_view.py
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from db.sqlite import get_conn, q


def _now_ts() -> int:
    return int(time.time())


def list_heal_deployments(namespace: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    """
    返回 deployment_uid 维度的状态列表：
    - status: normal | pending | circuit_open
    - fail_count, is_failing
    - pending_until_ts
    - last_action / last_reason / last_pod
    """
    ns = (namespace or "").strip()
    now = _now_ts()

    conn = get_conn()
    try:
        where = "WHERE 1=1"
        params: list[Any] = []
        if ns:
            where += " AND e.namespace = ?"
            params.append(ns)

        # ✅ 取每个 (namespace, deployment_uid) 最近一条 heal_events
        # 用 max(ts) 找到最新事件，再回表拿 last_* 字段
        sql = f"""
        WITH last_ts AS (
          SELECT
            namespace,
            deployment_uid,
            MAX(ts) AS ts
          FROM heal_events
          GROUP BY namespace, deployment_uid
        ),
        last_e AS (
          SELECT
            e.namespace,
            e.deployment_uid,
            e.deployment_name,
            e.fail_count,
            e.is_failing,
            e.ts AS last_event_ts,
            e.reason AS last_reason,
            e.action AS last_action,
            e.result AS last_result,
            e.pod AS last_pod
          FROM heal_events e
          INNER JOIN last_ts t
            ON e.namespace = t.namespace
           AND e.deployment_uid = t.deployment_uid
           AND e.ts = t.ts
        )
        SELECT
          e.namespace AS namespace,
          e.deployment_uid AS deployment_uid,

          -- 展示名：优先 state 的 deployment_name，其次 events 的
          COALESCE(s.deployment_name, e.deployment_name, 'unknown') AS deployment_name,

          -- 状态：优先 state（更权威），否则用 events 的
          COALESCE(s.fail_count, e.fail_count, 0) AS fail_count,
          COALESCE(s.is_failing, e.is_failing, 0) AS is_failing,

          e.last_event_ts,
          e.last_reason,
          e.last_action,
          e.last_result,
          e.last_pod,

          -- ✅ pending 来自 heal_pending 表
          COALESCE(p.pending, 0) AS pending,
          COALESCE(p.pending_until_ts, 0) AS pending_until_ts,
          COALESCE(p.last_action, '') AS pending_last_action,
          COALESCE(p.last_reason, '') AS pending_last_reason,
          COALESCE(p.last_pod, '') AS pending_last_pod,
          COALESCE(p.last_action_ts, 0) AS pending_set_ts

        FROM last_e e
        LEFT JOIN heal_state s
          ON e.namespace = s.namespace AND e.deployment_uid = s.deployment_uid
        LEFT JOIN heal_pending p
          ON e.namespace = p.namespace AND e.deployment_uid = p.deployment_uid

        {where}
        ORDER BY e.last_event_ts DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = q(conn, sql, params).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)

            is_failing = int(d.get("is_failing") or 0)
            pending = int(d.get("pending") or 0)
            pending_until = int(d.get("pending_until_ts") or 0)

            if is_failing == 1:
                status = "circuit_open"
            elif pending == 1 and pending_until > now:
                status = "pending"
            else:
                status = "normal"

            # pending 状态下，优先展示 pending 的 last_*
            if status == "pending":
                last_action = d.get("pending_last_action") or d.get("last_action") or ""
                last_reason = d.get("pending_last_reason") or d.get("last_reason") or ""
                last_pod = d.get("pending_last_pod") or d.get("last_pod") or ""
                last_ts = int(d.get("pending_set_ts") or d.get("last_event_ts") or 0)
            else:
                last_action = d.get("last_action") or ""
                last_reason = d.get("last_reason") or ""
                last_pod = d.get("last_pod") or ""
                last_ts = int(d.get("last_event_ts") or 0)

            out.append(
                {
                    "namespace": d.get("namespace") or "default",
                    "deployment_uid": d.get("deployment_uid") or "",
                    "deployment_name": d.get("deployment_name") or "unknown",
                    "status": status,
                    "fail_count": int(d.get("fail_count") or 0),
                    "is_failing": is_failing,
                    "pending_until_ts": pending_until if status == "pending" else 0,
                    "last_action": last_action,
                    "last_reason": last_reason,
                    "last_pod": last_pod,
                    "last_ts": last_ts,
                    "last_result": d.get("last_result") or "",
                }
            )

        return out
    finally:
        conn.close()


def get_heal_deployment_detail(namespace: str, deployment_uid: str) -> Dict[str, Any]:
    ns = (namespace or "default").strip() or "default"
    duid = (deployment_uid or "").strip()
    if not duid:
        return {"ok": False, "reason": "deployment_uid required"}

    # 只取这个 namespace 下的列表，然后找对应 uid
    items = list_heal_deployments(namespace=ns, limit=500, offset=0)
    for it in items:
        if it.get("deployment_uid") == duid:
            return {"ok": True, "item": it}
    return {"ok": False, "reason": "not found"}
