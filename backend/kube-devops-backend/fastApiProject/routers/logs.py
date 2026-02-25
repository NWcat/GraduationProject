# /routers/logs.py
from fastapi import APIRouter, Query, Depends
from services.monitoring.loki_client import query_logs_range, query_logs_instant
from routers.authz import require_user

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("/instant", dependencies=[Depends(require_user)])
def logs_instant(
    query: str = Query('{job=~".+"}'),
    limit: int = Query(50),
    time: str = Query(None),
    direction: str = Query("backward")
):
    return {"status": "success", "data": query_logs_instant(query, limit, time, direction)}

@router.get("/range", dependencies=[Depends(require_user)])
def logs_range(
    query: str = Query('{job=~".+"}'),
    minutes: int = Query(60),
    limit: int = Query(200),
    direction: str = Query("backward")
):
    return {"status": "success", "data": query_logs_range(query, minutes, limit, direction)}
