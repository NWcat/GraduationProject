# routers/ops_config.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException

from services.ops.runtime_config import (
    get_public_items,
    set_overrides,
    delete_override,
)

router = APIRouter(prefix="/api/ops/config", tags=["OpsConfig"])


@router.get("")
def get_config_items():
    """
    前端 Settings 页面：
    - value：生效值（secret 会脱敏）
    - default：后端默认（env/settings，secret 也脱敏）
    - has_override/source：是否被 DB 覆盖
    """
    return {"items": get_public_items()}


@router.put("")
def put_config_items(payload: Dict[str, Any] = Body(...)):
    """
    支持两种提交方式：
    1) { "PROMETHEUS_BASE": "xxx", "HEAL_EXECUTE": "1" }
    2) { "items": { "PROMETHEUS_BASE": "xxx" } }
    约定：v 为 "" 或 null -> 删除覆盖（回落默认）
    """
    pairs: Optional[Dict[str, Any]] = None

    if "items" in payload and isinstance(payload["items"], dict):
        pairs = payload["items"]
    else:
        pairs = payload

    if not isinstance(pairs, dict) or not pairs:
        raise HTTPException(status_code=400, detail="invalid payload")

    out = set_overrides(pairs)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out)
    return out


@router.delete("/{key}")
def delete_config_key(key: str):
    out = delete_override(key)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out)
    return out
