# routers/nodes.py
from __future__ import annotations

from fastapi import APIRouter

from services.nodes_service import list_nodes

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
def get_nodes():
    # 直接返回数组，前端最省事
    return list_nodes()