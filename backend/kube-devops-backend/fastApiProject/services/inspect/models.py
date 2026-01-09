# services/inspect/models.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


Level = Literal["ok", "warn", "error", "skip"]


class InspectItem(BaseModel):
    key: str
    title: str
    level: Level = "ok"
    detail: str = ""
    suggestion: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    durationMs: int = 0


class InspectSummary(BaseModel):
    total: int = 0
    ok: int = 0
    warn: int = 0
    error: int = 0
    skip: int = 0

    def add(self, level: Level) -> None:
        self.total += 1
        if level == "ok":
            self.ok += 1
        elif level == "warn":
            self.warn += 1
        elif level == "error":
            self.error += 1
        else:
            self.skip += 1


class InspectReport(BaseModel):
    runId: str
    updatedAt: str
    durationMs: int
    summary: InspectSummary
    items: List[InspectItem]
    meta: Dict[str, Any] = Field(default_factory=dict)
