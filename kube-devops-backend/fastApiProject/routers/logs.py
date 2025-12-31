# /routers/logs.py
from fastapi import APIRouter, Query
from services.loki_client import query_logs_range, query_logs_instant

router = APIRouter(prefix="/logs", tags=["Logs"])

@router.get("/instant")
def logs_instant(
    query: str = Query('{job=~".+"}'),
    limit: int = Query(50),
    time: str = Query(None),
    direction: str = Query("backward")
):
    return {"status": "success", "data": query_logs_instant(query, limit, time, direction)}

@router.get("/range")
def logs_range(
    query: str = Query('{job=~".+"}'),
    minutes: int = Query(60),
    limit: int = Query(200),
    direction: str = Query("backward")
):
    return {"status": "success", "data": query_logs_range(query, minutes, limit, direction)}
