# services/ops/heal_reset.py
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from db.utils.sqlite import get_conn, q
from services.ops.k8s_api import scale_deployment


def _get_state_for_reset(conn, namespace: str, deployment_uid: str) -> Tuple[Optional[str], Optional[int]]:
    """
    读取 heal_state 里：
    - deployment_name（用于 scale）
    - last_replicas（用于“用户留空=默认恢复”）
    """
    cur = q(
        conn,
        """
        SELECT deployment_name, last_replicas
        FROM heal_state
        WHERE namespace=? AND deployment_uid=?
        """,
        (namespace, deployment_uid),
    )
    row = cur.fetchone()
    if not row:
        return None, None
    dname = (row["deployment_name"] or "").strip() or None
    lr = row["last_replicas"]
    try:
        lr_i = None if lr is None else int(lr)
    except Exception:
        lr_i = None
    return dname, lr_i


def reset_heal_state(
    *,
    namespace: str,
    deployment_uid: str,
    restore_replicas: Optional[int] = None,
    deployment_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ✅ 默认逻辑（用户留空 = 后端默认逻辑）：
    - 若 restore_replicas is None：
        读取 heal_state.last_replicas
        有值：scale 回去
        没值：不动
    - 若用户传了 restore_replicas：
        直接按用户值 scale（优先级更高）

    注意：
    - 复位操作会 fail_count=0 / is_failing=0 / reason=''
    - 不会抹掉 last_replicas（保持，用于下次默认恢复）
    """
    ns = (namespace or "default").strip() or "default"
    duid = (deployment_uid or "").strip()
    if not duid:
        return {"ok": False, "reason": "deployment_uid required"}

    now = int(time.time())

    # 先用同一个连接把“默认恢复所需信息”读出来，避免你 UPSERT 覆盖 deployment_name
    conn = get_conn()
    try:
        state_dname, state_last_replicas = _get_state_for_reset(conn, ns, duid)

        # ✅ 决定最终用于 scale 的 deployment_name（优先：函数参数 > heal_state）
        final_deploy_name = (deployment_name or "").strip() or state_dname

        # ✅ 决定最终要恢复的副本数：
        #   用户传了就用用户的；否则用 heal_state.last_replicas；否则 None（不恢复）
        if restore_replicas is not None:
            try:
                final_replicas = int(restore_replicas)
            except Exception:
                final_replicas = 0
        else:
            final_replicas = state_last_replicas  # 可能是 None

        if final_replicas is not None and final_replicas < 0:
            final_replicas = 0

        # 1) ✅ 复位状态：fail_count=0, is_failing=0, reason=''
        #    不要把 last_replicas 清掉；deployment_name 也尽量别写空覆盖
        q(
            conn,
            """
            INSERT INTO heal_state(
              namespace, deployment_uid, deployment_name, fail_count, is_failing, reason, updated_ts, last_replicas
            )
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(namespace, deployment_uid) DO UPDATE SET
              deployment_name=CASE
                WHEN excluded.deployment_name IS NOT NULL AND excluded.deployment_name!='' THEN excluded.deployment_name
                ELSE heal_state.deployment_name
              END,
              fail_count=0,
              is_failing=0,
              reason='',
              updated_ts=excluded.updated_ts,
              last_replicas=heal_state.last_replicas
            """,
            (
                ns,
                duid,
                (deployment_name or "").strip(),
                0,
                0,
                "",
                now,
                None,  # insert 时 last_replicas 写 NULL；update 时保持旧值
            ),
        )

        # 2) ✅ 清 pending（必须）
        q(conn, "DELETE FROM heal_pending WHERE namespace=? AND deployment_uid=?", (ns, duid))

        # 3) （可选）清 heal_events 标记字段（历史表一致性）
        q(
            conn,
            "UPDATE heal_events SET fail_count=0, is_failing=0 WHERE namespace=? AND deployment_uid=?",
            (ns, duid),
        )

        conn.commit()
    finally:
        conn.close()

    out: Dict[str, Any] = {
        "ok": True,
        "namespace": ns,
        "deployment_uid": duid,
        "restored": False,
        "restore_source": "none",
    }

    # 4) ✅ 默认恢复：用户没传 restore_replicas => 用 last_replicas
    if restore_replicas is None:
        if final_replicas is None:
            # 没有 last_replicas：按你定义的默认逻辑“不动”
            out["restore_source"] = "none(last_replicas is null)"
            return out
        out["restore_source"] = "heal_state.last_replicas"
    else:
        out["restore_source"] = "user_input"

    # 需要恢复副本数时，deployment_name 必须存在（否则无法 patch deployment）
    if not final_deploy_name:
        out["restore_error"] = "deployment_name missing (param empty and heal_state.deployment_name empty)"
        return out

    try:
        detail = scale_deployment(namespace=ns, name=str(final_deploy_name), replicas=int(final_replicas))
        out["restored"] = True
        out["deployment_name"] = final_deploy_name
        out["restore_replicas"] = int(final_replicas)
        out["restore_detail"] = detail
    except Exception as e:
        out["restore_error"] = str(e)

    return out
