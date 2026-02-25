# services/tenants_service.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from db.utils.sqlite import get_conn, q, qmany
from services.users.service import ensure_user, gen_one_time_password
from services.k8s.tenant_ops import ensure_namespace, delete_namespace, ensure_rolebinding_admin, apply_resource_quota

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _tenant_row(conn, tenant_id: str) -> dict:
    t = q(conn, "SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
    if not t:
        raise ValueError("tenant not found")

    nss = q(conn, "SELECT namespace FROM tenant_namespaces WHERE tenant_id=? ORDER BY namespace",
            (tenant_id,)).fetchall()
    labels = q(conn, "SELECT k,v FROM tenant_labels WHERE tenant_id=? ORDER BY k",
               (tenant_id,)).fetchall()
    return {
        "id": t["id"],
        "name": t["name"],
        "status": t["status"],
        "adminUser": t["admin_user"],
        "namespaces": [x["namespace"] for x in nss],
        "labels": {x["k"]: x["v"] for x in labels},
        "quota": {"cpu": t["quota_cpu"], "memory": t["quota_mem"]},
        "createdAt": t["created_at"][:10],  # 你前端展示用日期
    }

def list_tenants(keyword: Optional[str], status: Optional[str]) -> list[dict]:
    conn = get_conn()
    where = []
    params = []
    if status:
        where.append("t.status=?")
        params.append(status)
    if keyword:
        kw = f"%{keyword.strip()}%"
        where.append("(t.name LIKE ? OR t.admin_user LIKE ? OR t.id LIKE ? OR EXISTS("
                     "SELECT 1 FROM tenant_namespaces ns WHERE ns.tenant_id=t.id AND ns.namespace LIKE ?))")
        params.extend([kw, kw, kw, kw])

    sql = "SELECT t.id FROM tenants t"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.created_at DESC"

    ids = [r["id"] for r in q(conn, sql, params).fetchall()]
    items = [_tenant_row(conn, tid) for tid in ids]
    conn.close()
    return items

def get_tenant(tenant_id: str) -> dict:
    conn = get_conn()
    out = _tenant_row(conn, tenant_id)
    conn.close()
    return out

def create_tenant(payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("name required")

    bind_ns = (payload.get("bindNamespace") or "").strip()
    auto_create_ns = payload.get("autoCreateNamespace", True)
    create_admin = bool(payload.get("createAdminUser", True))
    admin_username = (payload.get("adminUsername") or f"{name}-admin").strip()

    pwd_mode = payload.get("pwdMode", "auto")
    temp_pwd = payload.get("tempPassword")
    must_change = bool(payload.get("mustChangePassword", True))

    quota_cpu = (payload.get("quotaCpu") or "8").strip()
    quota_mem = (payload.get("quotaMem") or "16Gi").strip()

    tenant_id = "t-" + uuid.uuid4().hex[:8]
    now = _now_iso()

    one_time = None
    if create_admin:
        pwd = gen_one_time_password(pwd_mode, temp_pwd)
        ensure_user(admin_username, pwd, must_change=must_change)
        one_time = {"username": admin_username, "password": pwd}

    conn = get_conn()
    # unique name
    exists = q(conn, "SELECT 1 FROM tenants WHERE name=?", (name,)).fetchone()
    if exists:
        conn.close()
        raise ValueError("tenant name exists")

    q(conn, """
      INSERT INTO tenants(id, name, status, admin_user, created_at, quota_cpu, quota_mem)
      VALUES(?,?,?,?,?,?,?)
    """, (tenant_id, name, "active", admin_username, now, quota_cpu, quota_mem))

    if bind_ns:
        q(conn, "INSERT INTO tenant_namespaces(tenant_id, namespace) VALUES(?,?)",
          (tenant_id, bind_ns))

    conn.commit()
    conn.close()

    # 可选落地 K8s
    if bind_ns and auto_create_ns:
        ensure_namespace(bind_ns, labels={"tenant": name, "tenantId": tenant_id})
        if create_admin:
            ensure_rolebinding_admin(bind_ns, admin_username)
        apply_resource_quota(bind_ns, quota_cpu, quota_mem)

    return {"tenant": get_tenant(tenant_id), "oneTimePassword": one_time}

def delete_tenant(tenant_id: str, delete_namespaces: bool = False):
    conn = get_conn()
    # read namespaces before delete
    nss = [r["namespace"] for r in q(conn, "SELECT namespace FROM tenant_namespaces WHERE tenant_id=?",
                                    (tenant_id,)).fetchall()]
    # delete rows
    q(conn, "DELETE FROM tenants WHERE id=?", (tenant_id,))
    conn.commit()
    conn.close()

    if delete_namespaces:
        for ns in nss:
            try:
                delete_namespace(ns)
            except Exception:
                pass

def toggle_tenant(tenant_id: str) -> str:
    conn = get_conn()
    row = q(conn, "SELECT status FROM tenants WHERE id=?", (tenant_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("tenant not found")
    cur = row["status"]
    new_status = "active" if cur == "disabled" else "disabled"
    q(conn, "UPDATE tenants SET status=? WHERE id=?", (new_status, tenant_id))
    conn.commit()
    conn.close()
    return new_status

def upsert_labels(tenant_id: str, labels: dict) -> dict:
    conn = get_conn()
    # clear then insert (简单可靠)
    q(conn, "DELETE FROM tenant_labels WHERE tenant_id=?", (tenant_id,))
    rows = [(tenant_id, k, v) for k, v in labels.items()]
    if rows:
        qmany(conn, "INSERT INTO tenant_labels(tenant_id,k,v) VALUES(?,?,?)", rows)
    conn.commit()
    out = _tenant_row(conn, tenant_id)
    conn.close()
    return out["labels"]

def update_quota(tenant_id: str, cpu: str, memory: str) -> dict:
    conn = get_conn()
    q(conn, "UPDATE tenants SET quota_cpu=?, quota_mem=? WHERE id=?", (cpu, memory, tenant_id))
    # get namespaces for K8s apply
    nss = [r["namespace"] for r in q(conn, "SELECT namespace FROM tenant_namespaces WHERE tenant_id=?",
                                    (tenant_id,)).fetchall()]
    conn.commit()
    conn.close()

    # apply to K8s namespaces
    for ns in nss:
        try:
            apply_resource_quota(ns, cpu, memory)
        except Exception:
            pass

    return {"cpu": cpu, "memory": memory}

def bind_namespace(tenant_id: str, namespace: str, auto_create: bool = True) -> list[str]:
    ns = namespace.strip()
    if not ns:
        raise ValueError("namespace required")

    tenant = get_tenant(tenant_id)

    conn = get_conn()
    exists = q(conn, "SELECT 1 FROM tenant_namespaces WHERE tenant_id=? AND namespace=?",
               (tenant_id, ns)).fetchone()
    if not exists:
        q(conn, "INSERT INTO tenant_namespaces(tenant_id, namespace) VALUES(?,?)", (tenant_id, ns))
    conn.commit()
    # list namespaces
    nss = [r["namespace"] for r in q(conn, "SELECT namespace FROM tenant_namespaces WHERE tenant_id=? ORDER BY namespace",
                                    (tenant_id,)).fetchall()]
    conn.close()

    if auto_create:
        ensure_namespace(ns, labels={"tenant": tenant["name"], "tenantId": tenant_id})
        ensure_rolebinding_admin(ns, tenant["adminUser"])
        apply_resource_quota(ns, tenant["quota"]["cpu"], tenant["quota"]["memory"])

    return nss

def unbind_namespace(tenant_id: str, namespace: str) -> list[str]:
    ns = namespace.strip()
    conn = get_conn()
    q(conn, "DELETE FROM tenant_namespaces WHERE tenant_id=? AND namespace=?", (tenant_id, ns))
    conn.commit()
    nss = [r["namespace"] for r in q(conn, "SELECT namespace FROM tenant_namespaces WHERE tenant_id=? ORDER BY namespace",
                                    (tenant_id,)).fetchall()]
    conn.close()
    return nss

# Members
def list_members(tenant_id: str) -> list[dict]:
    conn = get_conn()
    rows = q(conn, """
      SELECT username,email,role,status,created_at
      FROM tenant_members WHERE tenant_id=?
      ORDER BY created_at DESC
    """, (tenant_id,)).fetchall()
    conn.close()
    return [{
        "username": r["username"],
        "email": r["email"],
        "role": r["role"],
        "status": r["status"],
        "createdAt": r["created_at"],
    } for r in rows]

def add_member(tenant_id: str, payload: dict) -> dict:
    username = (payload.get("username") or "").strip()
    if not username:
        raise ValueError("username required")
    email = (payload.get("email") or "").strip() or None
    role = payload.get("role", "viewer")
    pwd_mode = payload.get("pwdMode", "auto")
    temp_pwd = payload.get("tempPassword")
    must_change = bool(payload.get("mustChange", True))

    # 创建平台用户（你也可以改成：如果用户已存在就只绑定成员）
    pwd = gen_one_time_password(pwd_mode, temp_pwd)
    ensure_user(username, pwd, must_change=must_change)
    one_time = {"username": username, "password": pwd}

    conn = get_conn()
    # ensure tenant exists
    q(conn, "SELECT 1 FROM tenants WHERE id=?", (tenant_id,)).fetchone() or (_ for _ in ()).throw(ValueError("tenant not found"))

    exists = q(conn, "SELECT 1 FROM tenant_members WHERE tenant_id=? AND username=?",
               (tenant_id, username)).fetchone()
    if exists:
        conn.close()
        raise ValueError("member exists")

    q(conn, """
      INSERT INTO tenant_members(tenant_id, username, email, role, status, created_at)
      VALUES(?,?,?,?,?,?)
    """, (tenant_id, username, email, role, "active", _now_iso()))
    conn.commit()
    conn.close()

    member = {
        "username": username,
        "email": email,
        "role": role,
        "status": "active",
        "createdAt": _now_iso(),
    }
    return {"member": member, "oneTimePassword": one_time}

def change_member_role(tenant_id: str, username: str, role: str):
    conn = get_conn()
    q(conn, "UPDATE tenant_members SET role=? WHERE tenant_id=? AND username=?",
      (role, tenant_id, username))
    conn.commit()
    conn.close()

def remove_member(tenant_id: str, username: str):
    conn = get_conn()
    q(conn, "DELETE FROM tenant_members WHERE tenant_id=? AND username=?",
      (tenant_id, username))
    conn.commit()
    conn.close()