# /routers/alerts.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request

from services.alert_client import list_alerts
from services.ops.actions import apply_action
from services.ops.schemas import ApplyActionReq


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/list")
def get_alerts():
    return {"status": "success", "data": list_alerts()}


@router.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("收到告警:", data)
    return {"status": "ok"}
