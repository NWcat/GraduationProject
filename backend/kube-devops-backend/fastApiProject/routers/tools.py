# routers/tools.py
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from config import settings
from services.inspect.runner import run_inspection
from services.ops.runtime_config import get_value

router = APIRouter(prefix="/api/tools", tags=["tools"])


# -------------------------
# runtime config helpers
# priority: DB override > settings/.env > default
# -------------------------

def _to_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _rt_get(key: str) -> Tuple[Any, str]:
    """
    优先从 runtime_config.get_value 取（DB override 即刻生效）
    若 key 不在白名单或 runtime_config 出错，则回退 settings
    returns: (value, source) source in {"db","env","fallback"}
    """
    try:
        v, src = get_value(key)  # 白名单内：会查 DB；不在白名单：会回 env/default
        return v, src
    except Exception:
        return getattr(settings, key, None), "fallback"


def _rt_get_bool(key: str, default: bool) -> bool:
    v, _src = _rt_get(key)
    if v is None:
        v = getattr(settings, key, None)
    return _to_bool(v, default=default)


def _rt_get_str(key: str, default: str = "") -> str:
    v, _src = _rt_get(key)
    if v is None:
        v = getattr(settings, key, None)
    if v is None:
        return default
    return str(v).strip() or default


# -------------------------
# endpoints
# -------------------------

@router.get("/kubeconfig")
def download_kubeconfig():
    """
    下载 kubeconfig：
    - DB override 立即生效：ops_config(KUBECONFIG_PATH) > settings/.env > default
    """
    kubeconfig_path = _rt_get_str("KUBECONFIG_PATH", "")

    if not kubeconfig_path:
        raise HTTPException(status_code=400, detail="KUBECONFIG_PATH 未配置（可在运行时配置里覆盖）")

    p = Path(kubeconfig_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"kubeconfig 不存在：{p}")

    return FileResponse(
        path=str(p),
        filename="kubeconfig",
        media_type="application/octet-stream",
    )


@router.get("/inspect")
def inspect(
    format: str = Query("json", description="json 或 html"),
    include: Optional[str] = Query(None, description="逗号分隔：prom,nodes,system,pods,events,storage,dns"),
    save: bool = Query(True, description="是否落盘保存报告文件（data/reports）"),
    per_check_timeout_seconds: int = Query(5, ge=1, le=60),
    total_timeout_seconds: int = Query(25, ge=5, le=300),
    max_workers: int = Query(6, ge=1, le=32),
):
    """
    一键巡检
    - format=json：返回结构化结果
    - format=html：返回 HTML（同时也会落盘保存，若 save=true）
    """
    fmt = (format or "json").strip().lower()
    inc_list: List[str] = []
    if include:
        inc_list = [x.strip() for x in include.split(",") if x.strip()]

    # ✅ DB override 立即生效
    enable_prom = _rt_get_bool("INSPECT_ENABLE_PROM", True)

    out = run_inspection(
        enable_prom=enable_prom,
        include=inc_list,
        per_check_timeout_seconds=per_check_timeout_seconds,
        total_timeout_seconds=total_timeout_seconds,
        max_workers=max_workers,
        save_report=save,
    )
    report = out["report"]  # InspectReport
    paths = out.get("paths") or {}

    # 报告下载 URL（前端可用）
    report_url = ""
    json_url = ""
    if paths.get("html"):
        report_url = f"/api/tools/inspect/report/{report.runId}.html"
    if paths.get("json"):
        json_url = f"/api/tools/inspect/report/{report.runId}.json"

    if fmt == "html":
        return HTMLResponse(content=str(out.get("html") or ""), status_code=200)

    payload = report.model_dump()
    if report_url:
        payload["reportUrl"] = report_url
    if json_url:
        payload["jsonUrl"] = json_url
    return payload


@router.post("/inspect/run")
def inspect_run(
    include: Optional[str] = Query(None, description="逗号分隔：prom,nodes,system,pods,events,storage,dns"),
    per_check_timeout_seconds: int = Query(5, ge=1, le=60),
    total_timeout_seconds: int = Query(25, ge=5, le=300),
    max_workers: int = Query(6, ge=1, le=32),
):
    """
    给前端“一键巡检”按钮用：执行后返回 reportUrl/jsonUrl（可下载报告）。
    默认落盘保存 data/reports/{runId}.html/.json
    """
    inc_list: List[str] = []
    if include:
        inc_list = [x.strip() for x in include.split(",") if x.strip()]

    enable_prom = _rt_get_bool("INSPECT_ENABLE_PROM", True)

    out = run_inspection(
        enable_prom=enable_prom,
        include=inc_list,
        per_check_timeout_seconds=per_check_timeout_seconds,
        total_timeout_seconds=total_timeout_seconds,
        max_workers=max_workers,
        save_report=True,
    )
    report = out["report"]
    return {
        **report.model_dump(),
        "reportUrl": f"/api/tools/inspect/report/{report.runId}.html",
        "jsonUrl": f"/api/tools/inspect/report/{report.runId}.json",
    }


@router.get("/inspect/report/{filename}")
def download_report(filename: str):
    """
    下载巡检报告：html 或 json
    /api/tools/inspect/report/{runId}.html
    /api/tools/inspect/report/{runId}.json
    """
    base = Path("data") / "reports"
    p = base / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"report 不存在：{p}")

    if filename.endswith(".html"):
        return FileResponse(path=str(p), filename=filename, media_type="text/html; charset=utf-8")
    if filename.endswith(".json"):
        return FileResponse(path=str(p), filename=filename, media_type="application/json; charset=utf-8")

    raise HTTPException(status_code=400, detail="仅支持 .html 或 .json")


@router.get("/diagnostics")
def diagnostics_compat():
    """
    兼容旧接口：直接返回巡检 JSON（默认全量 include）
    """
    enable_prom = _rt_get_bool("INSPECT_ENABLE_PROM", True)
    out = run_inspection(enable_prom=enable_prom, include=[], save_report=False)
    report = out["report"]
    return report.model_dump()
