# services/ops/schemas.py
from __future__ import annotations

from pydantic import BaseModel
from typing import Dict, Any, Optional


class ApplyActionReq(BaseModel):
    action: str
    target: Dict[str, Any] = {}
    params: Dict[str, Any] = {}
    dry_run: bool = False


class ApplyActionResp(BaseModel):
    ok: bool
    action: str
    dry_run: bool
    detail: str = ""
    data: Dict[str, Any] = {}


class HealResetReq(BaseModel):
    namespace: str
    deployment_uid: str
    # 可选：你要 reset 顺带恢复副本时用
    deployment_name: Optional[str] = None
    restore_replicas: Optional[int] = None


class HealResetResp(BaseModel):
    ok: bool
    namespace: str
    deployment_uid: str
    restored: bool = False
    restore_replicas: Optional[int] = None
    restore_detail: Optional[str] = None
    restore_error: Optional[str] = None
