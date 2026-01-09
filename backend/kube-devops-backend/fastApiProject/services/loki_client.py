# /services/loki_client.py
import math
import hashlib
import re
from datetime import datetime, timedelta, timezone

import requests
from fastapi import HTTPException

from config import settings

# ✅ 兜底 selector：不要用 {}，改成 Loki 肯定有的 label
DEFAULT_SELECTOR = '{namespace=~".+"}'

# ✅ Loki 单条 time series 最大点数限制（报错里就是 11000）
LOKI_MAX_POINTS = 11000
# ✅ 最小 step，避免 1s 在长范围下爆点；也避免 0s
LOKI_MIN_STEP_SECONDS = 2


def _loki_base() -> str:
    """
    生效优先级：DB override（前端） > settings/.env > default
    你的 .env：
      LOKI_BASE=http://192.168.100.10:30356/loki/api/v1
    """
    base = ""

    # ✅ 正常路径：runtime_config 已封装 db/env 优先级
    try:
        from services.ops.runtime_config import get_value  # type: ignore

        v, _src = get_value("LOKI_BASE")
        base = str(v or "").strip()
    except Exception:
        # 兜底：runtime_config 不可用时回退 settings/.env
        base = str(getattr(settings, "LOKI_BASE", "") or "").strip()

    if not base:
        base = "http://localhost:3100/loki/api/v1"

    return base.rstrip("/")


def sanitize_logql(q: str) -> str:
    """
    目标：永远不要把 query 传成 {} 或空，避免 Loki 400
    兼容：=~".*" -> =~".+"
    """
    if q is None:
        return DEFAULT_SELECTOR

    s = str(q).strip()
    if not s:
        return DEFAULT_SELECTOR

    # ✅ 关键：把 {} / { } 兜底
    if re.fullmatch(r"\{\s*\}", s):
        return DEFAULT_SELECTOR

    # 你原来的替换留着（=~".*" -> =~".+"）
    s = re.sub(r'=~\s*"\s*\.\s*\*"', '=~".+"', s)

    return s


def _ns_to_timestr(ns: str) -> str:
    """
    Loki 返回的 ts 是 ns（纳秒）字符串。
    这里把它转换成“本机时区”的时间字符串（你当前平台显示的就是本机时区）
    - tz=UTC 表示这串 ns 是 UTC 时间轴上的绝对时间
    - astimezone() 不带参数：转换成本机时区（Windows 会跟随系统时区）
    """
    dt = datetime.fromtimestamp(int(ns) / 1e9, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _make_id(ts_ns: str, labels: dict, line: str) -> str:
    base = ts_ns + "|" + "|".join([f"{k}={labels.get(k,'')}" for k in sorted(labels.keys())]) + "|" + line
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def _normalize_stream_labels(stream: dict) -> dict:
    labels = {k: str(v) for k, v in (stream or {}).items()}
    mapped = dict(labels)

    # 常见别名兼容（你可按实际 promtail 标签调整）
    if "k8s_namespace" in labels and "namespace" not in mapped:
        mapped["namespace"] = labels["k8s_namespace"]
    if "k8s_pod" in labels and "pod" not in mapped:
        mapped["pod"] = labels["k8s_pod"]
    if "k8s_container" in labels and "container" not in mapped:
        mapped["container"] = labels["k8s_container"]

    if "stream" not in mapped:
        mapped["stream"] = labels.get("stream", "stdout")

    return mapped


def _request_loki(path: str, params: dict):
    """
    ✅ 不要 raise_for_status 直接炸 500
    Loki 400/500 的内容转成 HTTPException(detail)，前端能看到具体错误
    """
    url = f"{_loki_base()}{path}"
    try:
        resp = requests.get(url, params=params, timeout=10)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Loki request failed: {e}")

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return resp.json()


def _calc_step_seconds(start_ns: int, end_ns: int) -> int:
    """
    ✅ 核心修复：避免 exceeded maximum resolution of 11,000 points
    Loki 大致规则：range_seconds / step_seconds <= 11000
    """
    range_seconds = max(1, int((end_ns - start_ns) / 1e9))
    step = math.ceil(range_seconds / LOKI_MAX_POINTS)
    return max(LOKI_MIN_STEP_SECONDS, step)


def query_logs_instant(query: str, limit: int, time: str | None, direction: str):
    """
    Loki: /query
    返回 resultType=streams, result=[{stream:{...labels}, values:[[ts,line],...]}]
    """
    query = sanitize_logql(query)

    params = {"query": query, "limit": limit, "direction": direction}
    if time:
        params["time"] = time

    data = _request_loki("/query", params)

    items = []
    for r in data.get("data", {}).get("result", []):
        labels = _normalize_stream_labels(r.get("stream", {}))
        values = r.get("values", []) or []
        for ts_ns, line in values:
            items.append(
                {
                    "id": _make_id(ts_ns, labels, line),
                    "ts": _ns_to_timestr(ts_ns),
                    "stream": labels.get("stream", "stdout"),
                    "line": line,
                    "labels": labels,
                }
            )

    items.sort(key=lambda x: x["ts"], reverse=(direction == "backward"))
    return {"items": items}


def query_logs_range(query: str, minutes: int, limit: int, direction: str):
    """
    Loki: /query_range
    ✅ 修复点：step 不再写死 "1s"，而是按范围自动放大，避免 11000 points 报错
    """
    query = sanitize_logql(query)

    end = datetime.now(timezone.utc) - timedelta(seconds=5)
    start = end - timedelta(minutes=minutes)

    start_ns = int(start.timestamp() * 1e9)
    end_ns = int(end.timestamp() * 1e9)

    step_s = _calc_step_seconds(start_ns, end_ns)
    step = f"{step_s}s"

    params = {
        "query": query,
        "start": start_ns,
        "end": end_ns,
        "limit": limit,
        "direction": direction,
        "step": step,  # ✅关键：动态 step
    }

    data = _request_loki("/query_range", params)

    items = []
    for r in data.get("data", {}).get("result", []):
        labels = _normalize_stream_labels(r.get("stream", {}))
        values = r.get("values", []) or []
        for ts_ns, line in values:
            items.append(
                {
                    "id": _make_id(ts_ns, labels, line),
                    "ts": _ns_to_timestr(ts_ns),
                    "stream": labels.get("stream", "stdout"),
                    "line": line,
                    "labels": labels,
                }
            )

    items.sort(key=lambda x: x["ts"], reverse=(direction == "backward"))
    return {"items": items}
