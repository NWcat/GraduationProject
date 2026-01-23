# services/ops/healer.py
from __future__ import annotations

import json
import os
import socket
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from config import settings
from db.sqlite import get_conn, q
from services.ops.actions import apply_action
from services.ops.audit import log_heal_event
from services.ops.k8s_api import (
    list_pods,
    get_deployment_replicas,
    scale_deployment,
    deployment_exists,
)
from services.ops.schemas import ApplyActionReq
from services.alert_client import push_alert

from services.ops.runtime_config import get_heal_decay_config  # ✅ 新增
from services.ops.runtime_config import get_value as rc_get_value  # ✅ 生效值：DB override > env/settings > default

MAX_FAILURE_COUNT = 3  # 熔断阈值：>=3 进入熔断
HEAL_LOCK_TTL_SEC = 120
_DEPLOY_EXISTS_CACHE: Dict[Tuple[str, str, str], bool] = {}


def _split_csv(s: str) -> Set[str]:
    s = (s or "").strip()
    if not s:
        return set()
    return {x.strip() for x in s.split(",") if x.strip()}


def _rc_bool(key: str, default: bool) -> bool:
    try:
        v, _src = rc_get_value(key)
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off", ""):
            return False
        return bool(default)
    except Exception:
        return bool(default)


def _rc_int(key: str, default: int) -> int:
    try:
        v, _src = rc_get_value(key)
        return int(v)
    except Exception:
        return int(default)


def _rc_str(key: str, default: str) -> str:
    try:
        v, _src = rc_get_value(key)
        return str(v or "")
    except Exception:
        return str(default or "")


def _get_heal_lock_path() -> str:
    path = str(getattr(settings, "HEAL_LOCK_FILE", "") or os.environ.get("HEAL_LOCK_FILE", "")).strip()
    if path:
        return path
    return os.path.join(tempfile.gettempdir(), "kube-guard-heal.lock")


def get_heal_lock_owner_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _read_heal_lock() -> Optional[Dict[str, Any]]:
    path = _get_heal_lock_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _write_heal_lock(data: Dict[str, Any]) -> None:
    path = _get_heal_lock_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True)


def get_heal_lock_info() -> Optional[Dict[str, Any]]:
    return _read_heal_lock()


def acquire_heal_lock(owner: str, ttl_sec: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    path = _get_heal_lock_path()
    now = int(time.time())
    expire_at = now + max(1, int(ttl_sec))
    lock_data = {"owner": str(owner), "expire_at": int(expire_at)}

    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(lock_data, f, ensure_ascii=True)
        return True, lock_data
    except FileExistsError:
        existing = _read_heal_lock()
        if not existing:
            try:
                os.remove(path)
            except Exception:
                return False, None
            return acquire_heal_lock(owner, ttl_sec)

        existing_owner = str(existing.get("owner") or "")
        existing_expire = int(existing.get("expire_at") or 0)
        if existing_expire and now > existing_expire:
            try:
                os.remove(path)
            except Exception:
                return False, existing
            return acquire_heal_lock(owner, ttl_sec)

        if existing_owner == str(owner):
            _write_heal_lock(lock_data)
            return True, lock_data

        return False, existing
    except Exception:
        return False, None


def release_heal_lock(owner: str) -> None:
    path = _get_heal_lock_path()
    existing = _read_heal_lock()
    if not existing:
        return
    if str(existing.get("owner") or "") != str(owner):
        return
    try:
        os.remove(path)
    except Exception:
        pass


def _load_policy_sets() -> tuple[Set[str], Set[str]]:
    # ✅ 从 runtime_config 取“生效值”
    deny_raw = _rc_str("HEAL_DENY_NS", getattr(settings, "HEAL_DENY_NS", "kube-system,kube-public,kube-node-lease"))
    only_raw = _rc_str("HEAL_ONLY_REASONS", getattr(settings, "HEAL_ONLY_REASONS", ""))  # empty = all

    deny_ns = _split_csv(deny_raw)
    only_reasons = _split_csv(only_raw)
    return deny_ns, only_reasons


def _cooldown_key(namespace: str, key: str) -> str:
    return f"heal:cooldown:{namespace}:{key}"


def _alert_cooldown_key(kind: str, namespace: str, deployment_uid: str) -> str:
    return f"heal:alert:{kind}:{namespace}:{deployment_uid}"


def _get_last_ts(key: str) -> Optional[int]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT ts FROM ops_cooldown WHERE k=?", (key,))
        row = cur.fetchone()
        return None if not row else int(row["ts"])
    finally:
        conn.close()


def _set_last_ts(key: str, ts: int) -> None:
    conn = get_conn()
    try:
        q(
            conn,
            """
            INSERT INTO ops_cooldown(k, ts) VALUES(?, ?)
            ON CONFLICT(k) DO UPDATE SET ts=excluded.ts
            """,
            (key, int(ts)),
        )
        conn.commit()
    finally:
        conn.close()


def _get_deploy_state(namespace: str, deployment_uid: str) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = q(
            conn,
            "SELECT namespace, deployment_uid, deployment_name, fail_count, is_failing, reason FROM heal_state WHERE namespace=? AND deployment_uid=?",
            (namespace, deployment_uid),
        )
        row = cur.fetchone()
        if not row:
            return {"exists": False, "fail_count": 0, "is_failing": 0}
        return {
            "exists": True,
            "namespace": row["namespace"],
            "deployment_uid": row["deployment_uid"],
            "deployment_name": row["deployment_name"],
            "fail_count": int(row["fail_count"] or 0),
            "is_failing": int(row["is_failing"] or 0),
            "reason": row["reason"] or "",
        }
    finally:
        conn.close()


def _clear_deploy_state(namespace: str, deployment_uid: str) -> None:
    conn = get_conn()
    try:
        q(conn, "DELETE FROM heal_state WHERE namespace=? AND deployment_uid=?", (namespace, deployment_uid))
        q(conn, "DELETE FROM heal_pending WHERE namespace=? AND deployment_uid=?", (namespace, deployment_uid))
        conn.commit()
    finally:
        conn.close()


def _deployment_exists_cached(namespace: str, deployment_name: str, deployment_uid: str) -> bool:
    key = (namespace or "default", deployment_name or "", deployment_uid or "")
    if key in _DEPLOY_EXISTS_CACHE:
        return _DEPLOY_EXISTS_CACHE[key]
    exists = deployment_exists(namespace, deployment_name, expected_uid=deployment_uid)
    _DEPLOY_EXISTS_CACHE[key] = bool(exists)
    return bool(exists)


def _set_deploy_state(
    namespace: str,
    deployment_uid: str,
    deployment_name: str,
    fail_count: int,
    is_failing: int,
    reason: str,
    last_replicas: Optional[int] = None,
) -> None:
    if deployment_name and deployment_name != "unknown":
        if not _deployment_exists_cached(namespace, deployment_name, deployment_uid):
            _clear_deploy_state(namespace, deployment_uid)
            return
    conn = get_conn()
    try:
        now = int(time.time())
        q(
            conn,
            """
            INSERT INTO heal_state(
              namespace, deployment_uid, deployment_name,
              fail_count, is_failing, reason, updated_ts,
              last_replicas
            )
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(namespace, deployment_uid) DO UPDATE SET
              deployment_name=excluded.deployment_name,
              fail_count=excluded.fail_count,
              is_failing=excluded.is_failing,
              reason=excluded.reason,
              updated_ts=excluded.updated_ts,
              last_replicas=COALESCE(excluded.last_replicas, heal_state.last_replicas)
            """,
            (
                namespace,
                deployment_uid,
                deployment_name,
                int(fail_count),
                int(is_failing),
                str(reason or ""),
                now,
                (None if last_replicas is None else int(last_replicas)),
            ),
        )
        conn.commit()
    finally:
        conn.close()



def _reset_fail_and_close_circuit(namespace: str, deployment_uid: str) -> None:
    st = _get_deploy_state(namespace, deployment_uid)
    dname = st.get("deployment_name") or "unknown"
    _set_deploy_state(namespace, deployment_uid, dname, fail_count=0, is_failing=0, reason="")


def _decay_fail_count(namespace: str, deployment_uid: str, step: int) -> int:
    st = _get_deploy_state(namespace, deployment_uid)
    dname = st.get("deployment_name") or "unknown"
    cur = int(st.get("fail_count") or 0)
    new_val = max(cur - max(int(step), 1), 0)
    _set_deploy_state(
        namespace,
        deployment_uid,
        dname,
        fail_count=new_val,
        is_failing=0 if new_val < MAX_FAILURE_COUNT else int(st.get("is_failing") or 0),
        reason=st.get("reason") or "",
    )
    return new_val


def _get_pending(namespace: str, deployment_uid: str) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = q(
            conn,
            """
            SELECT * FROM heal_pending WHERE namespace=? AND deployment_uid=?
            """,
            (namespace, deployment_uid),
        )
        row = cur.fetchone()
        if not row:
            return {"exists": False}
        return dict(row)
    finally:
        conn.close()


def _set_pending(
    namespace: str,
    deployment_uid: str,
    pending_until_ts: int,
    deployment_name: str,
    last_action: str,
    last_action_ts: int,
    last_pod: str,
    last_pod_uid: str,
    last_reason: str,
) -> None:
    if deployment_name and deployment_name != "unknown":
        if not _deployment_exists_cached(namespace, deployment_name, deployment_uid):
            _clear_deploy_state(namespace, deployment_uid)
            return
    conn = get_conn()
    try:
        q(
            conn,
            """
            INSERT INTO heal_pending(namespace, deployment_uid, pending, pending_until_ts, deployment_name,
                                     last_action, last_action_ts, last_pod, last_pod_uid, last_reason)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(namespace, deployment_uid) DO UPDATE SET
              pending=excluded.pending,
              pending_until_ts=excluded.pending_until_ts,
              deployment_name=excluded.deployment_name,
              last_action=excluded.last_action,
              last_action_ts=excluded.last_action_ts,
              last_pod=excluded.last_pod,
              last_pod_uid=excluded.last_pod_uid,
              last_reason=excluded.last_reason
            """,
            (
                namespace,
                deployment_uid,
                1,
                int(pending_until_ts),
                deployment_name or "",
                last_action or "",
                int(last_action_ts),
                last_pod or "",
                last_pod_uid or "",
                last_reason or "",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _clear_pending(namespace: str, deployment_uid: str) -> None:
    conn = get_conn()
    try:
        q(conn, "DELETE FROM heal_pending WHERE namespace=? AND deployment_uid=?", (namespace, deployment_uid))
        conn.commit()
    finally:
        conn.close()


def _classify_reason(pod: Dict[str, Any]) -> str:
    """
    ✅ 从 list_pods() 的字段推断原因：
    - CrashLoopBackOff：container_statuses[*].waiting_reason 或 state.waiting.reason
    - NotReady：phase=Running 但 Ready condition != True
    其他情况返回空字符串（表示不处理）
    """
    # 1) CrashLoopBackOff / Waiting reason 优先
    for cs in (pod.get("container_statuses") or []):
        wr = (cs.get("waiting_reason") or "").strip()
        if wr:
            return wr

        st = cs.get("state") or {}
        waiting = st.get("waiting") or {}
        r2 = (waiting.get("reason") or "").strip()
        if r2:
            return r2

        terminated = st.get("terminated") or {}
        r3 = (terminated.get("reason") or "").strip()
        # terminated 原因很多，这里不强行当成异常原因；你想纳入再放开
        # if r3:
        #     return r3

    # 2) NotReady：Running 但 Ready!=True
    if (pod.get("phase") or "") == "Running":
        for c in (pod.get("conditions") or []):
            if c.get("type") == "Ready" and str(c.get("status")) != "True":
                return "NotReady"

    return ""



def _reason_allowed(reason: str, only_reasons: Set[str]) -> bool:
    if not only_reasons:
        return True
    return reason in only_reasons


def _send_circuit_open_periodic_alert(
    namespace: str, deployment_name: str, deployment_uid: str, fail_count: int, reason: str
) -> Dict[str, Any]:
    return push_alert(
        alertname="HealCircuitOpen",
        labels={
            "namespace": namespace,
            "deployment": deployment_name,
            "deployment_uid": deployment_uid,
            "severity": "warning",
        },
        annotations={
            "summary": "Heal circuit is open; auto-heal is paused",
            "description": f"fail_count={fail_count}, reason={reason}",
        },
    )


def _send_circuit_open_alert(
    namespace: str,
    deployment_name: str,
    deployment_uid: str,
    fail_count: int,
    reason: str,
    action_taken: str,
) -> Dict[str, Any]:
    return push_alert(
        alertname="HealCircuitOpened",
        labels={
            "namespace": namespace,
            "deployment": deployment_name,
            "deployment_uid": deployment_uid,
            "severity": "critical",
        },
        annotations={
            "summary": "Heal circuit opened; auto-heal paused",
            "description": f"action={action_taken}, fail_count={fail_count}, reason={reason}",
        },
    )


def _circuit_break(
    namespace: str,
    deployment_uid: str,
    deployment_name: str,
    pod_name: str,
    pod_uid: str,
    controller_kind: Optional[str],
    dry_run: bool,
) -> Dict[str, Any]:
    if dry_run:
        log_heal_event(
            namespace=namespace,
            deployment_uid=deployment_uid,
            deployment_name=deployment_name,
            pod=pod_name,
            pod_uid=pod_uid,
            reason="circuit_open",
            action="circuit_break",
            result="dry_run",
            fail_count_inc=0,
        )
        return {"ok": True, "dry_run": True, "action": "would_scale0_and_delete"}

    action_taken: List[str] = []
    errors: List[str] = []

    # ✅ 裸 Pod：直接 delete（不做 deployment 熔断状态机）
    if not controller_kind:
        try:
            req = ApplyActionReq(
                action="DELETE_POD",
                target={"namespace": namespace, "pod": pod_name},
                params={},
                dry_run=False,
            )
            apply_action(req)
            action_taken.append("delete_pod")
            result = "deleted_bare_pod"
        except Exception as e:
            errors.append(f"delete_failed:{e}")
            result = "delete_failed"

        log_heal_event(
            namespace=namespace,
            deployment_uid=deployment_uid,
            deployment_name=deployment_name,
            pod=pod_name,
            pod_uid=pod_uid,
            reason="circuit_open",
            action="circuit_break:" + ",".join(action_taken or ["none"]),
            result=result,
            fail_count_inc=0,
        )
        return {"ok": (len(errors) == 0), "dry_run": False, "controller_kind": controller_kind, "actions": action_taken, "errors": errors}

    # ✅ 非 ReplicaSet 控制器：不做 scale（避免越权/无意义）
    if controller_kind != "ReplicaSet":
        log_heal_event(
            namespace=namespace,
            deployment_uid=deployment_uid,
            deployment_name=deployment_name,
            pod=pod_name,
            pod_uid=pod_uid,
            reason="circuit_open",
            action="circuit_break:none",
            result=f"skip_controller:{controller_kind}",
            fail_count_inc=0,
        )
        return {"ok": False, "dry_run": False, "controller_kind": controller_kind, "actions": [], "errors": [f"skip_controller:{controller_kind}"]}

    # ✅ ReplicaSet（Deployment 管理）：先 scale=0，再 delete pod
    scale_ok = False
    before_replicas: Optional[int] = None
    if deployment_name and deployment_name != "unknown":
        # ✅ 在 scale=0 前读取“熔断前副本数”并写入 heal_state.last_replicas
        try:
            before_replicas = get_deployment_replicas(namespace, deployment_name)
        except Exception:
            before_replicas = None

        try:
            # ✅ 熔断关键路径：直接走 k8s_api（比 apply_action 的 target 校验更稳）
            detail = scale_deployment(namespace=namespace, name=deployment_name, replicas=0)
            action_taken.append("scale_deployment:0")
            action_taken.append(f"scale_detail:{detail}")
            scale_ok = True
        except Exception as e:
            errors.append(f"scale_failed:{e}")
    else:
        errors.append("scale_skipped:deployment_name_unknown")

    try:
        req = ApplyActionReq(
            action="DELETE_POD",
            target={"namespace": namespace, "pod": pod_name},
            params={},
            dry_run=False,
        )
        apply_action(req)
        action_taken.append("delete_pod")
    except Exception as e:
        errors.append(f"delete_failed:{e}")

    if scale_ok:
        _set_deploy_state(
            namespace,
            deployment_uid,
            deployment_name,
            fail_count=MAX_FAILURE_COUNT,
            is_failing=1,  # ✅ 只有 scale 成功才开熔断
            reason="circuit_open",
            last_replicas=before_replicas,  # ✅ 记录熔断前副本数（供 reset 自动恢复）
        )
        result = "opened"
    else:
        _set_deploy_state(
            namespace,
            deployment_uid,
            deployment_name,
            fail_count=MAX_FAILURE_COUNT,
            is_failing=0,
            reason="circuit_open_failed:" + ";".join(errors or ["unknown"]),
            # last_replicas 不传 => 不覆盖旧值
        )
        result = "open_failed"

    log_heal_event(
        namespace=namespace,
        deployment_uid=deployment_uid,
        deployment_name=deployment_name,
        pod=pod_name,
        pod_uid=pod_uid,
        reason="circuit_open",
        action="circuit_break:" + ",".join(action_taken or ["none"]),
        result=result,
        fail_count_inc=0,
    )

    return {"ok": scale_ok, "dry_run": False, "controller_kind": controller_kind, "actions": action_taken,
            "errors": errors}


def _process_pending_heals(
    pods: List[Dict[str, Any]], now_ts: int, dry_run: bool, namespace: Optional[str] = None
) -> Dict[str, Any]:
    """
    阶段①：对 pending 验收窗口做闭环：
    - 若恢复：清 pending，并根据配置决定 reset 或 decay fail_count
    - 若仍异常：唯一入口 fail_count +1，并可能触发熔断
    """
    decay_enabled, decay_step = get_heal_decay_config()

    # ✅ 生效值读取（runtime_config 没纳管就回退 settings 默认）
    verify_sec = _rc_int("HEAL_VERIFY_SEC", int(getattr(settings, "HEAL_VERIFY_SEC", 30)))
    alert_cooldown_sec = _rc_int("HEAL_ALERT_COOLDOWN_SEC", int(getattr(settings, "HEAL_ALERT_COOLDOWN_SEC", 300)))

    processed = 0
    recovered = 0
    failed_verify = 0
    circuit_opened = 0
    details: List[Dict[str, Any]] = []

    conn = get_conn()
    try:
        if namespace:
            cur = q(conn, "SELECT * FROM heal_pending WHERE namespace=?", (namespace,))
        else:
            cur = q(conn, "SELECT * FROM heal_pending", ())
        pendings = cur.fetchall()
    finally:
        conn.close()

    pod_index: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for p in pods:
        ns = p.get("namespace", "default")
        duid = p.get("deployment_uid") or "unknown"
        if duid == "unknown":
            continue
        pod_index.setdefault((ns, duid), []).append(p)

    for row in pendings:
        r = dict(row)  # ✅ sqlite3.Row -> dict，后面就可以 .get()

        ns = r.get("namespace") or "default"
        duid = r.get("deployment_uid") or "unknown"
        if namespace and ns != namespace:
            continue

        processed += 1

        pending_until_ts = int(r.get("pending_until_ts") or 0)
        if now_ts < pending_until_ts:
            continue

        dname = r.get("deployment_name") or "unknown"
        last_action = r.get("last_action") or ""
        last_pod = r.get("last_pod") or ""
        last_pod_uid = r.get("last_pod_uid") or "unknown"
        last_reason = r.get("last_reason") or ""

        if dname != "unknown" and not _deployment_exists_cached(ns, dname, duid):
            _clear_deploy_state(ns, duid)
            details.append(
                {
                    "namespace": ns,
                    "deployment_uid": duid,
                    "deployment_name": dname,
                    "pending": "cleared_missing",
                }
            )
            continue


        bad_list = pod_index.get((ns, duid), [])
        bad = None
        for p in bad_list:
            r = _classify_reason(p)
            if r:
                bad = {"sample_pod": p, "reason": r}
                break

        if bad is None:
            if decay_enabled:
                new_fail = _decay_fail_count(ns, duid, step=decay_step)
                result = "recovered_decay"
            else:
                _reset_fail_and_close_circuit(ns, duid)
                new_fail = 0
                result = "recovered"

            _clear_pending(ns, duid)
            recovered += 1

            log_heal_event(
                namespace=ns,
                deployment_uid=duid,
                deployment_name=dname,
                pod=last_pod,
                pod_uid=last_pod_uid,
                reason=last_reason,
                action=last_action,
                result=result,
                fail_count_inc=0,
            )

            details.append(
                {
                    "namespace": ns,
                    "deployment_uid": duid,
                    "deployment_name": dname,
                    "pending": "recovered",
                    "fail_count_after": new_fail,
                    "decay_enabled": decay_enabled,
                    "decay_step": decay_step,
                }
            )
            continue

        sample = bad["sample_pod"]
        reason_now = bad["reason"]
        pod_name_now = sample.get("name", last_pod)
        pod_uid_now = sample.get("pod_uid") or last_pod_uid
        controller_kind = sample.get("controller_kind")

        st0 = _get_deploy_state(ns, duid)
        prev_fail = int(st0.get("fail_count") or 0)
        prev_failing = int(st0.get("is_failing") or 0)

        fail_count_now = prev_fail + 1

        # ✅ 只推进 fail_count；is_failing 仍保持原值（按 A：只有 scale 成功才置 1）
        _set_deploy_state(
            ns,
            duid,
            dname,
            fail_count=fail_count_now,
            is_failing=prev_failing,
            reason=reason_now,
        )

        failed_verify += 1
        _clear_pending(ns, duid)

        # ✅ 事件只做审计记录，不再承担“状态推进”
        log_heal_event(
            namespace=ns,
            deployment_uid=duid,
            deployment_name=dname,
            pod=pod_name_now,
            pod_uid=pod_uid_now,
            reason=reason_now,
            action=last_action,
            result="verify_failed",
            fail_count_inc=0,  # ✅ 状态已由 heal_state 推进
        )

        cb = None
        alert = None
        if (not dry_run) and fail_count_now >= MAX_FAILURE_COUNT:
            cb = _circuit_break(
                namespace=ns,
                deployment_uid=duid,
                deployment_name=dname,
                pod_name=pod_name_now,
                pod_uid=pod_uid_now,
                controller_kind=controller_kind,
                dry_run=dry_run,
            )
            circuit_opened += 1

            action_taken = str(cb.get("actions") or cb.get("action") or "circuit_break")
            alert = _send_circuit_open_alert(
                namespace=ns,
                deployment_name=dname,
                deployment_uid=duid,
                fail_count=fail_count_now,
                reason=reason_now,
                action_taken=action_taken,
            )
            _set_last_ts(_alert_cooldown_key("circuit_open", ns, duid), now_ts)

        details.append(
            {
                "namespace": ns,
                "deployment_uid": duid,
                "deployment_name": dname,
                "pending": "still_bad",
                "reason": reason_now,
                "fail_count": fail_count_now,
                "circuit_breaker": cb,
                "alert": alert,
            }
        )

    return {
        "processed": processed,
        "recovered": recovered,
        "failed_verify": failed_verify,
        "circuit_opened": circuit_opened,
        "details": details,
    }




def run_heal_scan_once(namespace: Optional[str] = None) -> Dict[str, Any]:
    # ✅ 生效值读取（DB override > env/settings > default）
    enabled = _rc_bool("HEAL_ENABLED", bool(getattr(settings, "HEAL_ENABLED", True)))
    if not enabled:
        return {"ok": False, "reason": "HEAL_ENABLED=0", "checked": 0, "healed": 0, "details": []}

    _DEPLOY_EXISTS_CACHE.clear()

    execute = _rc_bool("HEAL_EXECUTE", bool(getattr(settings, "HEAL_EXECUTE", False)))
    max_per_cycle = _rc_int("HEAL_MAX_PER_CYCLE", int(getattr(settings, "HEAL_MAX_PER_CYCLE", 3)))
    cooldown_sec = _rc_int("HEAL_COOLDOWN_SEC", int(getattr(settings, "HEAL_COOLDOWN_SEC", 300)))

    # runtime_config 没纳管就回退
    verify_sec = _rc_int("HEAL_VERIFY_SEC", int(getattr(settings, "HEAL_VERIFY_SEC", 30)))
    alert_cooldown_sec = _rc_int("HEAL_ALERT_COOLDOWN_SEC", int(getattr(settings, "HEAL_ALERT_COOLDOWN_SEC", 300)))

    deny_ns, only_reasons = _load_policy_sets()

    pods = list_pods(namespace=namespace)
    checked = len(pods)

    dry_run = (not execute)
    healed = 0
    skipped = 0
    attempted = 0
    details: List[Dict[str, Any]] = []

    now_ts = int(time.time())

    pending_report = _process_pending_heals(pods=pods, now_ts=now_ts, dry_run=dry_run, namespace=namespace)
    if pending_report["processed"] > 0:
        details.append({"stage": "process_pending", **pending_report})

    for p in pods:
        ns = p.get("namespace", "default")
        name = p.get("name", "")
        pod_uid = p.get("pod_uid") or "unknown"
        controller_kind = p.get("controller_kind")

        deployment_name = p.get("deployment_name") or "unknown"
        deployment_uid = p.get("deployment_uid") or "unknown"

        if controller_kind == "ReplicaSet" and deployment_uid == "unknown":
            skipped += 1
            details.append({"namespace": ns, "pod": name, "skipped": True, "reason": "missing_deployment_uid"})
            continue

        heal_key_uid = deployment_uid if (controller_kind == "ReplicaSet" and deployment_uid != "unknown") else pod_uid

        if ns in deny_ns:
            skipped += 1
            details.append({"namespace": ns, "pod": name, "skipped": True, "reason": "namespace_denied"})
            continue

        reason = _classify_reason(p)
        if not reason:
            skipped += 1
            details.append({"namespace": ns, "pod": name, "skipped": True, "reason": "no_reason_found"})
            continue

        if not _reason_allowed(reason, only_reasons):
            skipped += 1
            details.append({"namespace": ns, "pod": name, "skipped": True, "reason": "reason_not_allowed"})
            continue

        ck = _cooldown_key(ns, heal_key_uid)
        last_ts = _get_last_ts(ck)
        if last_ts is not None and (now_ts - int(last_ts)) < cooldown_sec:
            skipped += 1
            details.append({"namespace": ns, "pod": name, "skipped": True, "reason": reason, "cooldown": True})
            continue

        st = _get_deploy_state(ns, heal_key_uid)

        if st["exists"] and st["is_failing"] == 1:
            ak = _alert_cooldown_key("circuit_open", ns, heal_key_uid)
            last_alert_ts = _get_last_ts(ak)
            should_alert = (last_alert_ts is None) or ((now_ts - int(last_alert_ts)) >= alert_cooldown_sec)

            alert = None
            if should_alert:
                alert = _send_circuit_open_periodic_alert(
                    namespace=ns,
                    deployment_name=st.get("deployment_name") or deployment_name,
                    deployment_uid=heal_key_uid,
                    fail_count=int(st.get("fail_count") or 0),
                    reason=st.get("reason") or reason,
                )
                _set_last_ts(ak, now_ts)

            skipped += 1
            details.append(
                {
                    "namespace": ns,
                    "pod": name,
                    "skipped": True,
                    "reason": reason,
                    "circuit_open": True,
                    "deployment_uid": heal_key_uid,
                    "deployment_name": deployment_name,
                    "fail_count": st["fail_count"],
                    "alert": alert,
                }
            )
            continue

        pend = _get_pending(ns, heal_key_uid)
        if pend.get("exists") and int(pend.get("pending") or 0) == 1 and now_ts < int(pend.get("pending_until_ts") or 0):
            skipped += 1
            details.append(
                {
                    "namespace": ns,
                    "pod": name,
                    "skipped": True,
                    "reason": reason,
                    "pending": True,
                    "pending_until_ts": int(pend.get("pending_until_ts") or 0),
                }
            )
            continue

        log_heal_event(
            namespace=ns,
            deployment_uid=heal_key_uid,
            deployment_name=deployment_name,
            pod=name,
            pod_uid=pod_uid,
            reason=reason,
            action="scan",
            result="detected",
            fail_count_inc=0,
        )

        if not controller_kind:
            skipped += 1
            details.append({"namespace": ns, "pod": name, "reason": reason, "result": "bare_pod_skip"})
            continue

        try:
            req = ApplyActionReq(
                action="DELETE_POD",
                target={"namespace": ns, "pod": name},
                params={},
                dry_run=dry_run,
            )
            resp = apply_action(req)

            attempted += 1
            _set_last_ts(ck, now_ts)

            if not dry_run:
                healed += 1
                _set_pending(
                    namespace=ns,
                    deployment_uid=heal_key_uid,
                    pending_until_ts=now_ts + verify_sec,
                    deployment_name=deployment_name,
                    last_action="delete_pod",
                    last_action_ts=now_ts,
                    last_pod=name,
                    last_pod_uid=pod_uid,
                    last_reason=reason,
                )
                log_heal_event(
                    namespace=ns,
                    deployment_uid=heal_key_uid,
                    deployment_name=deployment_name,
                    pod=name,
                    pod_uid=pod_uid,
                    reason=reason,
                    action="delete_pod",
                    result="pending",
                    fail_count_inc=0,
                )
            else:
                log_heal_event(
                    namespace=ns,
                    deployment_uid=heal_key_uid,
                    deployment_name=deployment_name,
                    pod=name,
                    pod_uid=pod_uid,
                    reason=reason,
                    action="delete_pod",
                    result="dry_run",
                    fail_count_inc=0,
                )

            details.append(
                {
                    "namespace": ns,
                    "pod": name,
                    "deployment_name": deployment_name,
                    "deployment_uid": heal_key_uid,
                    "controller_kind": controller_kind,
                    "reason": reason,
                    "dry_run": dry_run,
                    "result": "dry_run" if dry_run else "pending",
                    "pending_until_ts": (now_ts + verify_sec) if (not dry_run) else None,
                    "detail": resp.detail,
                    "action": resp.model_dump(),
                }
            )

        except Exception as e:
            details.append({"namespace": ns, "pod": name, "reason": reason, "result": "failed", "detail": str(e)})

        if attempted >= max_per_cycle:
            break

    return {
        "ok": True,
        "checked": checked,
        "healed": healed,
        "dry_run": dry_run,
        "attempted": attempted,
        "skipped": skipped,
        "max_per_cycle": max_per_cycle,
        "cooldown_sec": cooldown_sec,
        "verify_sec": verify_sec,
        "alert_cooldown_sec": alert_cooldown_sec,
        "deny_ns": sorted(list(deny_ns)),
        "only_reasons": sorted(list(only_reasons)),
        "details": details,
    }
