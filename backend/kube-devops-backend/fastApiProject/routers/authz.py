# routers/authz.py
from __future__ import annotations

from fastapi import Header, HTTPException

from routers.auth import get_current_username


def require_user(authorization: str = Header(default="")) -> str:
    try:
        return get_current_username(authorization)
    except HTTPException:
        raise HTTPException(status_code=401, detail="未授权")


def require_admin(authorization: str = Header(default="")) -> str:
    username = require_user(authorization)
    if username != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    return username
