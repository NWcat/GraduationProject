# /services/ai/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field


class TsPoint(BaseModel):
    ts: int = Field(..., description="unix timestamp seconds")
    value: float


class BandPoint(BaseModel):
    ts: int
    yhat: float
    yhat_lower: float
    yhat_upper: float


class ErrorMetrics(BaseModel):
    mae: float = 0.0
    rmse: float = 0.0
    mape: float = 0.0
    note: str = ""


class CpuHistoryResp(BaseModel):
    node: str
    minutes: int
    step: int
    series: List[TsPoint]
    meta: Dict[str, Any] = Field(default_factory=dict)


class CpuForecastResp(BaseModel):
    node: str
    history_minutes: int
    horizon_minutes: int
    step: int
    history: List[TsPoint]
    forecast: List[BandPoint]
    metrics: ErrorMetrics
    meta: Dict[str, Any] = Field(default_factory=dict)


# === append to services/ai/schemas.py ===
# 你已有 TsPoint / BandPoint / ErrorMetrics，就不要重复定义
# 这里只新增 Mem / PodCpu 的响应模型

class MemHistoryResp(BaseModel):
    node: str
    minutes: int
    step: int
    series: List[TsPoint]
    meta: Dict[str, Any] = Field(default_factory=dict)


class MemForecastResp(BaseModel):
    node: str
    history_minutes: int
    horizon_minutes: int
    step: int
    history: List[TsPoint]
    forecast: List[BandPoint]
    metrics: ErrorMetrics
    meta: Dict[str, Any] = Field(default_factory=dict)


class PodCpuHistoryResp(BaseModel):
    namespace: str
    pod: str
    minutes: int
    step: int
    series: List[TsPoint]
    meta: Dict[str, Any] = Field(default_factory=dict)


class PodCpuForecastResp(BaseModel):
    namespace: str
    pod: str
    history_minutes: int
    horizon_minutes: int
    step: int
    history: List[TsPoint]
    forecast: List[BandPoint]
    metrics: ErrorMetrics
    meta: Dict[str, Any] = Field(default_factory=dict)


class AnomalyPoint(BaseModel):
    ts: int
    actual: float
    expected: float
    upper: float
    lower: float
    residual: float
    score: float
    is_anomaly: bool
    reason: Optional[str] = None


class AnomalyResp(BaseModel):
    target: Literal["node_cpu", "node_mem", "pod_cpu"]
    key: str
    window_minutes: int
    step: int
    anomalies: List[AnomalyPoint]
    meta: Optional[Dict[str, Any]] = None


class ActionHint(BaseModel):
    kind: Literal[
        "scale_hpa",
        "scale_deployment",
        "restart_deployment",
        "add_node",
        "cordon_node",
        "restart_pod",
        "delete_pod",
        "investigate_logs",
        "tune_requests_limits",
        "enable_rate_limit",
        "no_action",
    ]
    params: Dict[str, Any] = {}


class SuggestionItem(BaseModel):
    severity: Literal["info", "warning", "critical"]
    title: str
    evidence: Dict[str, Any] = {}
    rationale: str
    action: ActionHint


class SuggestionsResp(BaseModel):
    target: Literal["node_cpu", "node_mem", "pod_cpu"]
    key: str
    suggestions: List[SuggestionItem]
    suggestion_id: Optional[str] = None
    llm_summary: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class AssistantChatReq(BaseModel):
    message: str
    page: Optional[str] = None
    context: Dict[str, Any] = {}
    use_llm: bool = True


class AssistantChatResp(BaseModel):
    reply: str
    suggestions: Optional[SuggestionsResp] = None
    anomalies: Optional[AnomalyResp] = None
    meta: Optional[Dict[str, Any]] = None


class FeedbackReq(BaseModel):
    target: Literal["node_cpu", "node_mem", "pod_cpu"]
    key: str
    action_kind: str
    outcome: Literal["success", "fail", "ignored"]
    detail: Optional[str] = None
    suggestion_id: Optional[str] = None
    ts: Optional[int] = None


class EvolutionParams(BaseModel):
    observe_ratio: float
    trigger_ratio: float
    critical_ratio: float
    sustain_minutes: int


class EvolutionResp(BaseModel):
    target: str
    key: str
    enabled: bool
    params: EvolutionParams
    source: str


class FeedbackResp(BaseModel):
    ok: bool
    feedback_id: Optional[int] = None
    evolved: bool = False
    evolution: Optional[EvolutionResp] = None
