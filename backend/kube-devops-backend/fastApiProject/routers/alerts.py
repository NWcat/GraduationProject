# /routers/alerts.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, HTTPException, Query, Depends

from db.alerts.repo import normalize_fingerprint, upsert_alert, list_alerts as list_platform_alerts, get_alert
from services.notification.feishu_client import push_alert_async
from routers.authz import require_user


router = APIRouter(prefix="/api/alerts", tags=["Alerts"])
# compat: legacy /alerts/* paths
alias_router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.post("/webhook")
@alias_router.post("/webhook")  # compat: legacy path
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid payload")

    alerts = data.get("alerts") if isinstance(data, dict) else None
    if not isinstance(alerts, list):
        raise HTTPException(status_code=400, detail="invalid alerts payload")

    upserted = 0
    for a in alerts:
        if not isinstance(a, dict):
            continue
        labels = a.get("labels") or {}
        annotations = a.get("annotations") or {}
        status = str(a.get("status") or "")
        starts_at = str(a.get("startsAt") or "")
        ends_at = str(a.get("endsAt") or "")
        fp = normalize_fingerprint(fingerprint=a.get("fingerprint"), labels=labels)
        upsert_alert(
            fingerprint=fp,
            status=status or "firing",
            labels=labels if isinstance(labels, dict) else {},
            annotations=annotations if isinstance(annotations, dict) else {},
            starts_at=starts_at,
            ends_at=ends_at,
            source="alertmanager",
        )
        push_alert_async(
            {
                "fingerprint": fp,
                "status": status or "firing",
                "labels": labels if isinstance(labels, dict) else {},
                "annotations": annotations if isinstance(annotations, dict) else {},
                "starts_at": starts_at,
                "ends_at": ends_at,
                "source": "alertmanager",
            }
        )
        upserted += 1

    return {"ok": True, "upserted": upserted}


def _center_list_impl(
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    return list_platform_alerts(status=status, source=source, limit=limit, offset=offset)


@router.get("/center/list", dependencies=[Depends(require_user)])
@alias_router.get("/center/list", dependencies=[Depends(require_user)])  # compat: legacy path
def center_list(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return _center_list_impl(status=status, source=source, limit=limit, offset=offset)


@router.get("/list", dependencies=[Depends(require_user)])
@alias_router.get("/list", dependencies=[Depends(require_user)])  # compat: legacy path
def list_compat(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    result = _center_list_impl(status=status, source=source, limit=limit, offset=offset)
    if not isinstance(result, dict):
        return {
            "items": [],
            "limit": limit,
            "offset": offset,
            "deprecated": True,
            "message": "deprecated: use /api/alerts/center/list",
        }
    payload = dict(result)
    payload["deprecated"] = True
    payload["message"] = "deprecated: use /api/alerts/center/list"
    if "items" not in payload:
        payload["items"] = []
    if "limit" not in payload:
        payload["limit"] = limit
    if "offset" not in payload:
        payload["offset"] = offset
    return payload


@router.get("/center/{alert_id}", dependencies=[Depends(require_user)])
@alias_router.get("/center/{alert_id}", dependencies=[Depends(require_user)])  # compat: legacy path
def center_detail(alert_id: int):
    alert = get_alert(int(alert_id))
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    return {"alert": alert}
