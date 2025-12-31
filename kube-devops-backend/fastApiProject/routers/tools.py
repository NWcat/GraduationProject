# routers/tools.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from services.prometheus_client import instant_value

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/kubeconfig")
def download_kubeconfig():
    """
    直接把本地 KUBECONFIG_PATH 当文件下载（适合你现在 Windows 开发）
    """
    if not settings.KUBECONFIG_PATH:
        raise HTTPException(status_code=400, detail="KUBECONFIG_PATH 未配置")

    p = Path(settings.KUBECONFIG_PATH)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"kubeconfig 不存在：{p}")

    return FileResponse(
        path=str(p),
        filename="kubeconfig",
        media_type="application/octet-stream",
    )


@router.get("/diagnostics")
def diagnostics():
    """
    轻量诊断：用 Prometheus 的 instant query 生成几个关键健康项
    你毕设展示很够用了
    """
    now = datetime.now(timezone.utc).isoformat()

    # 1) Prometheus 是否可查询到 up（泛化写法）
    any_up = float(instant_value("sum(up)", 0.0) or 0.0)
    prom_ok = any_up > 0

    # 2) CPU（%）—— 推荐：按 instance 聚合再 avg，避免多核/多机混乱
    cpu = float(
        instant_value('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))', 0.0) or 0.0
    )

    # 3) 内存（%）—— 推荐用 node exporter 的 MemAvailable / MemTotal（更合理）
    mem = float(
        instant_value(
            '100 * (1 - (sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes)))',
            0.0,
        )
        or 0.0
    )

    # 4) Kubelet targets（如果你 Prometheus 有抓 kubelet）
    kubelet_up = float(instant_value('sum(up{job=~".*kubelet.*"})', 0.0) or 0.0)

    items = [
        {
            "key": "prometheus",
            "title": "Prometheus 采集状态",
            "level": "ok" if prom_ok else "error",
            "detail": "Prometheus 可用（up > 0）" if prom_ok else "Prometheus 不可用或无数据",
        },
        {
            "key": "kubelet",
            "title": "Kubelet 目标状态",
            "level": "ok" if kubelet_up >= 1 else "warn",
            "detail": f"kubelet up targets: {kubelet_up:.0f}",
        },
        {
            "key": "cpu",
            "title": "CPU 使用率",
            "level": "ok" if cpu < 70 else ("warn" if cpu < 90 else "error"),
            "detail": f"{cpu:.1f}%",
        },
        {
            "key": "memory",
            "title": "内存使用率",
            "level": "ok" if mem < 70 else ("warn" if mem < 90 else "error"),
            "detail": f"{mem:.1f}%",
        },
    ]

    return {"updatedAt": now, "items": items}
