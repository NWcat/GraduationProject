# services/auth_service.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt


def _get_runtime_value(key: str):
    """
    生效优先级：DB override（前端） > settings/.env > default
    runtime_config 不可用时回退 settings
    """
    try:
        from services.ops.runtime_config import get_value  # type: ignore

        return get_value(key)  # (value, source)
    except Exception:
        try:
            from config import settings  # type: ignore

            return getattr(settings, key, None), "env"
        except Exception:
            return None, "default"


def _get_str(key: str, default: str = "") -> str:
    v, _ = _get_runtime_value(key)
    s = str(v or "").strip()
    return s if s else default


def _get_int(key: str, default: int) -> int:
    v, _ = _get_runtime_value(key)
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _jwt_secret() -> str:
    # ✅ default 必须是一个可用值，但强烈建议你在 .env/DB 里覆盖
    return _get_str("JWT_SECRET", "CHANGE_ME_TO_SOMETHING_RANDOM")


def _jwt_alg() -> str:
    # ✅ 白名单一下，避免写入乱值导致 jose 报错
    alg = _get_str("JWT_ALG", "HS256")
    if alg not in ("HS256", "HS384", "HS512"):
        alg = "HS256"
    return alg


def _jwt_expire_min() -> int:
    v = _get_int("JWT_EXPIRE_MIN", 720)
    if v < 5:
        v = 5
    if v > 60 * 24 * 30:
        v = 60 * 24 * 30  # 最长 30 天，防止配置写炸
    return v


def create_access_token(subject: str, extra: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=_jwt_expire_min())
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if extra:
        payload.update(extra)

    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_alg())


def decode_token(token: str) -> dict:
    return jwt.decode(token, _jwt_secret(), algorithms=[_jwt_alg()])
