from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Depends

from services.k8s.kube_client import get_core_v1
from routers.authz import require_user

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get("/list", dependencies=[Depends(require_user)])
def list_events(
    namespace: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    continue_token: str | None = Query(None, alias="continue"),
):
    try:
        v1 = get_core_v1()
        if namespace:
            resp = v1.list_namespaced_event(
                namespace=namespace,
                limit=limit,
                _continue=continue_token,
            )
        else:
            resp = v1.list_event_for_all_namespaces(
                limit=limit,
                _continue=continue_token,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"list events failed: {e}")

    items = []
    for e in resp.items or []:
        obj = e.involved_object
        items.append(
            {
                "type": str(e.type or ""),
                "reason": str(e.reason or ""),
                "message": str(e.message or ""),
                "count": int(e.count or 0),
                "first_timestamp": str(e.first_timestamp.isoformat() if e.first_timestamp else ""),
                "last_timestamp": str(e.last_timestamp.isoformat() if e.last_timestamp else ""),
                "namespace": str(obj.namespace or ""),
                "kind": str(obj.kind or ""),
                "name": str(obj.name or ""),
            }
        )

    cont = ""
    try:
        cont = str(resp.metadata._continue or "")
    except Exception:
        cont = ""
    return {"items": items, "continue": cont}

