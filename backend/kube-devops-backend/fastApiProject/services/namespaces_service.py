# services/namespaces_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from kubernetes.client.rest import ApiException

from db.sqlite import get_conn, q
from services.kube_client import get_core_v1


SYSTEM_NS_DENYLIST = {
    "default",
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "kubernetes-dashboard",
    # 你可按需加：monitoring / logging / ingress-nginx 等
}

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ensure_tables():
    """
    你 init_db 已经建了 namespaces_registry，但为了幂等与独立使用，保留这个也没坏处
    """
    conn = get_conn()
    q(conn, """
    CREATE TABLE IF NOT EXISTS namespaces_registry (
      name TEXT PRIMARY KEY,
      managed INTEGER NOT NULL DEFAULT 0,
      managed_by_tenant_id TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    """)
    q(conn, "CREATE INDEX IF NOT EXISTS idx_ns_registry_tenant ON namespaces_registry(managed_by_tenant_id);")
    conn.commit()
    conn.close()

def list_namespace_options() -> List[str]:
    api = get_core_v1()
    items = api.list_namespace().items
    return sorted([x.metadata.name for x in items])

def list_namespaces(keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_tables()

    # 1) 先读 registry（sqlite）
    conn = get_conn()
    cur = q(conn, "SELECT name, managed, managed_by_tenant_id FROM namespaces_registry")
    reg_rows = cur.fetchall()
    conn.close()

    reg_map: Dict[str, Dict[str, Any]] = {}
    for r in reg_rows:
        # r 是 sqlite3.Row，可 dict-like
        reg_map[r["name"]] = {
            "managed": bool(int(r["managed"] or 0)),
            "managedByTenantId": r["managed_by_tenant_id"],
        }

    # 2) 再读 k8s namespace 列表
    api = get_core_v1()
    items = api.list_namespace().items

    out: List[Dict[str, Any]] = []
    for ns in items:
        name = ns.metadata.name
        labels = ns.metadata.labels or {}
        created_at = ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None
        phase = ns.status.phase if ns.status else None

        system = (name in SYSTEM_NS_DENYLIST) or name.startswith("kube-")
        reg = reg_map.get(name)

        out.append({
            "name": name,
            "labels": labels,
            "phase": phase,
            "createdAt": created_at,
            "system": system,
            "managed": bool(reg["managed"]) if reg else False,
            "managedByTenantId": reg["managedByTenantId"] if reg else None,
        })

    # 3) keyword 过滤（支持 name / labels key=value）
    if keyword:
        kw = keyword.strip().lower()

        def hit(x: Dict[str, Any]) -> bool:
            if kw in (x["name"] or "").lower():
                return True
            for k, v in (x.get("labels") or {}).items():
                s = f"{k}={v}".lower()
                if kw in s or kw in k.lower() or kw in str(v).lower():
                    return True
            return False

        out = [x for x in out if hit(x)]

    out.sort(key=lambda x: x["name"])
    return out

def create_namespace(
    name: str,
    labels: Optional[Dict[str, str]] = None,
    managed: bool = True,
    managed_by_tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    幂等：namespace 已存在 -> 视为成功；并 upsert registry
    """
    ensure_tables()
    api = get_core_v1()

    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    # 1) k8s create (idempotent)
    existed = True
    try:
        api.read_namespace(name)
    except ApiException as e:
        if e.status == 404:
            existed = False
        else:
            raise HTTPException(status_code=500, detail=f"k8s error: {e}")

    if not existed:
        body = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": name, "labels": labels or {}},
        }
        try:
            api.create_namespace(body=body)
        except ApiException as e:
            if e.status != 409:
                raise HTTPException(status_code=500, detail=f"create namespace failed: {e}")

    # 2) registry upsert
    conn = get_conn()
    now = _now_iso()

    # 如果已存在，保留 created_at
    cur = q(conn, "SELECT created_at FROM namespaces_registry WHERE name=?", (name,))
    row = cur.fetchone()
    created_at = row["created_at"] if row else now

    q(conn, """
    INSERT OR REPLACE INTO namespaces_registry
      (name, managed, managed_by_tenant_id, created_at, updated_at)
    VALUES (?,?,?,?,?)
    """, (name, 1 if managed else 0, managed_by_tenant_id, created_at, now))

    conn.commit()
    conn.close()

    # 3) 返回该 ns 的展示结构
    for it in list_namespaces(keyword=name):
        if it["name"] == name:
            return it
    return {"name": name}

def patch_namespace_labels(name: str, labels: Dict[str, str]) -> Dict[str, Any]:
    """
    labels 是全量替换（patch merge）；你也可以改成 merge 增量
    """
    api = get_core_v1()
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    body = {"metadata": {"labels": labels or {}}}
    try:
        api.patch_namespace(name=name, body=body)
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="namespace not found")
        raise HTTPException(status_code=500, detail=f"patch labels failed: {e}")

    for it in list_namespaces(keyword=name):
        if it["name"] == name:
            return it
    return {"name": name}

def delete_namespace(name: str, purge_registry: bool = True) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    if (name in SYSTEM_NS_DENYLIST) or name.startswith("kube-"):
        raise HTTPException(status_code=403, detail=f"system namespace forbidden: {name}")

    api = get_core_v1()
    try:
        api.delete_namespace(name=name)
    except ApiException as e:
        # 幂等：不存在也算成功
        if e.status != 404:
            raise HTTPException(status_code=500, detail=f"delete namespace failed: {e}")

    if purge_registry:
        ensure_tables()
        conn = get_conn()
        q(conn, "DELETE FROM namespaces_registry WHERE name=?", (name,))
        conn.commit()
        conn.close()

    return {"ok": True}
