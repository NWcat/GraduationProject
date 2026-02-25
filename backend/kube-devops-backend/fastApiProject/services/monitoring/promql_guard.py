# services/promql_guard.py
from __future__ import annotations

import os
import re
from fastapi import HTTPException

PROM_MAX_RANGE_MINUTES = 1440
PROM_MIN_STEP_SECONDS = 15
PROM_MAX_POINTS = 11000


def _to_bool(v: str, default: bool = False) -> bool:
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def free_promql_enabled() -> bool:
    # 1) DB override（runtime_config）优先
    try:
        from services.ops import runtime_config
        val, _ = runtime_config.get_value("PROMQL_FREE_ENABLED")

        # bool 类型直接返回
        if isinstance(val, bool):
            return val

        # 数字：0/0.0 -> False，其它 -> True
        if isinstance(val, (int, float)):
            return val != 0

        # 字符串等：用 _to_bool 解析（"0"/"false"/"off" -> False）
        if val is None:
            return False
        return _to_bool(str(val), default=False)
    except Exception:
        pass

    # 2) settings/.env 回退
    try:
        from config import settings
        v = getattr(settings, "PROMQL_FREE_ENABLED", False)

        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return v != 0
        if v is None:
            return False
        return _to_bool(str(v), default=False)
    except Exception:
        # 3) 最后回退到环境变量
        return _to_bool(os.getenv("PROMQL_FREE_ENABLED", "false"), default=False)



def validate_promql(query: str) -> None:
    if free_promql_enabled():
        return
    pattern = (
        r"^[a-zA-Z_:][a-zA-Z0-9_:]*"
        r"(?:\{[a-zA-Z_][a-zA-Z0-9_]*=\"[^\"]*\""
        r"(?:,[a-zA-Z_][a-zA-Z0-9_]*=\"[^\"]*\")*\})?"
        r"(?:\[[0-9]+[smhdwy]\])?$"
    )
    if re.fullmatch(pattern, query or "") is None:
        raise HTTPException(status_code=400, detail="PromQL 已禁用，仅允许简单指标查询")


def validate_range(start: float, end: float, step: int) -> None:
    if end <= start:
        raise HTTPException(status_code=400, detail="时间范围非法")
    if step < PROM_MIN_STEP_SECONDS:
        raise HTTPException(status_code=400, detail="step 过小")
    range_seconds = end - start
    if range_seconds > PROM_MAX_RANGE_MINUTES * 60:
        raise HTTPException(status_code=400, detail="时间范围超出限制")
    points = range_seconds / step
    if points > PROM_MAX_POINTS:
        raise HTTPException(status_code=400, detail="数据点过多")
