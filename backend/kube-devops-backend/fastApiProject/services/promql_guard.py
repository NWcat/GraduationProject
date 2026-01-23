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
