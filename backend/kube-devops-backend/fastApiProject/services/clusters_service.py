# services/clusters_service.py
from __future__ import annotations

import time
import pathlib
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db.sqlite import get_conn, q
from services.kube_client import validate_kubeconfig_content


def list_clusters() -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT * FROM clusters ORDER BY is_active DESC, id DESC", ())
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": int(r["id"]),
                    "name": str(r["name"] or ""),
                    "type": str(r["type"] or ""),
                    "provider": str(r["provider"] or ""),
                    "is_active": int(r["is_active"] or 0),
                    "created_ts": int(r["created_ts"] or 0),
                    "updated_ts": int(r["updated_ts"] or 0),
                }
            )
        return out
    finally:
        conn.close()


def get_active_cluster() -> Optional[Dict[str, Any]]:
    """
    返回当前 active 集群（若没有则 None）
    """
    conn = get_conn()
    try:
        cur = q(conn, "SELECT * FROM clusters WHERE is_active=1 ORDER BY id DESC LIMIT 1", ())
        r = cur.fetchone()
        if not r:
            return None
        return {
            "id": int(r["id"]),
            "name": str(r["name"] or ""),
            "type": str(r["type"] or ""),
            "provider": str(r["provider"] or ""),
            "is_active": int(r["is_active"] or 0),
            "created_ts": int(r["created_ts"] or 0),
            "updated_ts": int(r["updated_ts"] or 0),
        }
    finally:
        conn.close()


def verify_cluster(kubeconfig_text: str) -> Dict[str, Any]:
    """
    仅校验 kubeconfig 是否可连通，不入库
    """
    kubeconfig_text = (kubeconfig_text or "").strip()
    if not kubeconfig_text:
        raise HTTPException(400, "kubeconfig is required")

    try:
        test = validate_kubeconfig_content(kubeconfig_text)
    except Exception as e:
        raise HTTPException(400, f"kubeconfig validate failed: {e}")

    return {"ok": True, "test": test}


def add_cluster(name: str, cluster_type: str, provider: str, kubeconfig_text: str) -> Dict[str, Any]:
    name = (name or "").strip()
    cluster_type = (cluster_type or "").strip()
    provider = (provider or "").strip()
    kubeconfig_text = (kubeconfig_text or "").strip()

    if not name:
        raise HTTPException(400, "name is required")
    if cluster_type not in ("self-hosted", "managed"):
        raise HTTPException(400, "type must be self-hosted or managed")
    if not kubeconfig_text:
        raise HTTPException(400, "kubeconfig is required")

    # ✅ 先试连，避免存进来才发现不可用
    try:
        test = validate_kubeconfig_content(kubeconfig_text)
    except Exception as e:
        raise HTTPException(400, f"kubeconfig validate failed: {e}")

    now = int(time.time())

    conn = get_conn()
    try:
        q(
            conn,
            """
            INSERT INTO clusters(name, type, provider, kubeconfig, is_active, created_ts, updated_ts)
            VALUES(?,?,?,?,?,?,?)
            """,
            (name, cluster_type, provider, kubeconfig_text, 0, now, now),
        )
        conn.commit()

        cur = q(conn, "SELECT last_insert_rowid() AS id", ())
        new_id = int(cur.fetchone()["id"])
        return {"ok": True, "id": new_id, "test": test}
    finally:
        conn.close()


def delete_cluster(cluster_id: int) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT id, is_active FROM clusters WHERE id=?", (int(cluster_id),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "cluster not found")
        if int(row["is_active"] or 0) == 1:
            raise HTTPException(400, "cannot delete active cluster; switch away first")

        q(conn, "DELETE FROM clusters WHERE id=?", (int(cluster_id),))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def activate_cluster(cluster_id: int) -> Dict[str, Any]:
    """
    ✅ 单活多集群：激活某个集群
    - 把 kubeconfig 写到 data/kubeconfigs/cluster_<id>.yaml
    - ops_config 覆盖 KUBE_MODE=kubeconfig + KUBECONFIG_PATH
    - clusters.is_active 切换为 1
    """
    conn = get_conn()
    try:
        cur = q(conn, "SELECT * FROM clusters WHERE id=?", (int(cluster_id),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "cluster not found")

        kubeconfig_text = str(row["kubeconfig"] or "").strip()
        if not kubeconfig_text:
            raise HTTPException(400, "kubeconfig empty in DB")

        # ✅ 先 verify 一次（激活前兜底）
        try:
            test = validate_kubeconfig_content(kubeconfig_text)
        except Exception as e:
            raise HTTPException(400, f"kubeconfig validate failed: {e}")

        # ✅ 落盘（原子写：先写 tmp 再 replace）
        base = pathlib.Path("data") / "kubeconfigs"
        base.mkdir(parents=True, exist_ok=True)

        cfg_path = base / f"cluster_{int(cluster_id)}.yaml"
        tmp_path = base / f".cluster_{int(cluster_id)}.yaml.tmp"

        tmp_path.write_text(kubeconfig_text, encoding="utf-8")
        tmp_path.replace(cfg_path)  # atomic on same filesystem

        # ✅ DB：清空旧 active，再置新 active
        now = int(time.time())
        q(conn, "UPDATE clusters SET is_active=0", ())
        q(conn, "UPDATE clusters SET is_active=1, updated_ts=? WHERE id=?", (now, int(cluster_id)))

        # ✅ 写 ops_config 覆盖（你的 kube_client 会检测到变化后 reload）
        q(
            conn,
            """
            INSERT INTO ops_config(k, v, updated_ts) VALUES(?,?,?)
            ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_ts=excluded.updated_ts
            """,
            ("KUBE_MODE", "kubeconfig", now),
        )
        q(
            conn,
            """
            INSERT INTO ops_config(k, v, updated_ts) VALUES(?,?,?)
            ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_ts=excluded.updated_ts
            """,
            ("KUBECONFIG_PATH", str(cfg_path.as_posix()), now),
        )

        conn.commit()

        return {
            "ok": True,
            "active_cluster_id": int(cluster_id),
            "kubeconfig_path": str(cfg_path.as_posix()),
            "test": test,
        }
    finally:
        conn.close()
