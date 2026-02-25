# routers/data.py
from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict, Optional

from services.monitoring.loki_client import query_logs_range
from services.alerts.client import list_alerts
from services.monitoring.prometheus_client import range_by_minutes
from services.monitoring.promql_guard import validate_promql

router = APIRouter(prefix="/api/data", tags=["Data"])

@router.get("")
def get_data(
    type: str = Query("all", description="数据类型: logs / metrics / alerts / all"),
    pod: Optional[str] = Query(None, description="Pod 名称"),
    namespace: Optional[str] = Query(None, description="K8s 命名空间"),
    metric: str = Query("up", description="Prometheus 查询语句（PromQL）"),
    minutes: int = Query(5, ge=1, le=1440, description="最近多少分钟"),
    limit: int = Query(50, ge=1, le=500, description="日志最大条数"),
):
    """
    聚合查询 API（迁移版）
    - type=logs/metrics/alerts/all
    - pod/namespace 用于过滤日志和指标
    - 指标数据走 Prometheus query_range（range_by_minutes）
    """
    result: Dict[str, Any] = {}

    # LogQL
    logql_parts = []
    if namespace:
        logql_parts.append(f'namespace="{namespace}"')
    if pod:
        logql_parts.append(f'pod=~"{pod}.*"')
    logql_query = "{" + ",".join(logql_parts) + "}" if logql_parts else '{job=~".+"}'

    if type in ["logs", "all"]:
        result["logs"] = query_logs_range(logql_query, minutes, limit, "backward")

    if type in ["metrics", "all"]:
        prom_query = metric
        validate_promql(prom_query)

        # 如果 metric 本身没带 {}，才自动追加 label 过滤
        label_filters = []
        if namespace:
            label_filters.append(f'namespace="{namespace}"')
        if pod:
            label_filters.append(f'pod=~"{pod}.*"')

        if label_filters and "{" not in metric:
            prom_query = f'{metric}{{{",".join(label_filters)}}}'

        # ✅ 用你新 client 的 range_by_minutes（底层走 /api/v1/query_range）
        result["metrics"] = range_by_minutes(prom_query, minutes=minutes, step=30)

    if type in ["alerts", "all"]:
        result["alerts"] = list_alerts()

    return {
        "status": "success",
        "filters": {
            "type": type,
            "pod": pod,
            "namespace": namespace,
            "metric": metric,
            "minutes": minutes,
            "limit": limit,
        },
        "data": result,
    }
