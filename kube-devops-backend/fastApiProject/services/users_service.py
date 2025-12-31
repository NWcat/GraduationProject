# services/users_service.py
from __future__ import annotations
import base64, os, hashlib
from datetime import datetime, timezone
from typing import Optional
import hmac

from db.sqlite import get_conn, q

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _gen_password(len_: int = 14) -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*"
    return "".join(chars[os.urandom(1)[0] % len(chars)] for _ in range(len_))

def _hash_password(pwd: str) -> str:
    # PBKDF2-HMAC-SHA256
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt, 120_000)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()

def ensure_user(username: str, password: str, must_change: bool = True):
    conn = get_conn()
    row = q(conn, "SELECT username FROM users WHERE username=?", (username,)).fetchone()
    if row:
        conn.close()
        return

    q(conn, """
      INSERT INTO users(username, password_hash, must_change, status, created_at)
      VALUES(?,?,?,?,?)
    """, (username, _hash_password(password), 1 if must_change else 0, "active", _now_iso()))
    conn.commit()
    conn.close()

def reset_password(username: str) -> dict:
    conn = get_conn()
    row = q(conn, "SELECT username FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        # 用户不存在也可以选择创建；这里更符合你平台：直接报错
        conn.close()
        raise ValueError("user not found")

    pwd = _gen_password(14)
    q(conn, "UPDATE users SET password_hash=?, must_change=1 WHERE username=?",
      (_hash_password(pwd), username))
    conn.commit()
    conn.close()
    return {"username": username, "password": pwd}

def toggle_user(username: str) -> str:
    conn = get_conn()
    row = q(conn, "SELECT status FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("user not found")

    cur = row["status"]
    new_status = "active" if cur == "disabled" else "disabled"
    q(conn, "UPDATE users SET status=? WHERE username=?", (new_status, username))
    conn.commit()
    conn.close()
    return new_status

def gen_one_time_password(mode: str, manual: Optional[str] = None) -> str:
    if mode == "manual":
        if not manual or not manual.strip():
            raise ValueError("tempPassword required for manual mode")
        return manual.strip()
    return _gen_password(14)

def _verify_password(pwd: str, stored: str) -> bool:
    """
    stored 格式：pbkdf2$<salt_b64>$<dk_b64>
    """
    try:
        algo, salt_b64, dk_b64 = stored.split("$", 2)
        if algo != "pbkdf2":
            return False
        salt = base64.b64decode(salt_b64.encode())
        dk_stored = base64.b64decode(dk_b64.encode())
        dk = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt, 120_000)
        return hmac.compare_digest(dk, dk_stored)
    except Exception:
        return False


def get_user(username: str) -> Optional[dict]:
    conn = get_conn()
    row = q(conn, "SELECT username, password_hash, must_change, status, created_at FROM users WHERE username=?",
            (username,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "username": row["username"],
        "password_hash": row["password_hash"],
        "must_change": bool(row["must_change"]),
        "status": row["status"],
        "created_at": row["created_at"],
    }


def verify_user_password(username: str, password: str) -> dict:
    """
    成功：返回 user dict
    失败：抛 ValueError
    """
    user = get_user(username)
    if not user:
        raise ValueError("invalid credentials")
    if user["status"] != "active":
        raise ValueError("user disabled")
    if not _verify_password(password, user["password_hash"]):
        raise ValueError("invalid credentials")
    return user

def update_user_password(username: str, old_password: str, new_password: str) -> dict:
    """
    校验旧密码 -> 更新新密码 -> must_change 置 0
    返回更新后的 user（不含 hash）
    """
    user = get_user(username)
    if not user:
        raise ValueError("user not found")
    if user["status"] != "active":
        raise ValueError("user disabled")
    if not _verify_password(old_password, user["password_hash"]):
        raise ValueError("invalid old password")

    if not new_password or len(new_password.strip()) < 6:
        raise ValueError("password too short")

    conn = get_conn()
    q(conn, "UPDATE users SET password_hash=?, must_change=0 WHERE username=?",
      (_hash_password(new_password.strip()), username))
    conn.commit()
    conn.close()

    # 重新取一次
    updated = get_user(username)
    return {
        "username": updated["username"],
        "status": updated["status"],
        "must_change": updated["must_change"],
    }

