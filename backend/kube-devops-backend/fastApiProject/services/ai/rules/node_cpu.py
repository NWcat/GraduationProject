from __future__ import annotations

from typing import Literal, Optional

from services.ai.schemas import SuggestionItem, ActionHint

from .registry import register_rule
from .types import RuleContext, RuleResult, _get_attr, _max_yhat, _sustain_over_threshold_minutes, _to_int


@register_rule(name="node_cpu_basic", target="node_cpu", priority=100)
def rule_node_cpu(ctx: RuleContext) -> RuleResult:
    node = ctx.node or ctx.key
    forecast = ctx.forecast
    threshold = float(ctx.threshold if ctx.threshold is not None else 85.0)
    sustain_minutes = int(ctx.sustain_minutes if ctx.sustain_minutes is not None else 15)

    points = _get_attr(forecast, "forecast", []) or []
    step = _to_int(_get_attr(forecast, "step", 60), 60)

    peak = _max_yhat(points)
    sustain_over = _sustain_over_threshold_minutes(points, float(threshold), step)

    if sustain_over < int(sustain_minutes):
        return SuggestionItem(
            severity="info",
            title="节点 CPU 预测未达到持续超阈值条件",
            evidence={
                "node": node,
                "peak": round(peak, 2),
                "threshold": threshold,
                "sustain_over_minutes": sustain_over,
                "required_sustain_minutes": sustain_minutes,
            },
            rationale="预测峰值或持续时间不足以触发动作建议。",
            action=ActionHint(kind="no_action", params={}),
        )

    severity: Literal["info", "warning", "critical"] = "warning"
    if peak >= min(100.0, threshold + 10.0):
        severity = "critical"

    return SuggestionItem(
        severity=severity,
        title="节点 CPU 持续高负载，建议排查与扩容",
        evidence={
            "node": node,
            "peak": round(peak, 2),
            "threshold": threshold,
            "sustain_over_minutes": sustain_over,
        },
        rationale="预测显示 CPU 将持续高于阈值，可能导致调度拥塞/延迟上升。",
        action=ActionHint(kind="add_node", params={"node": node}),
    )
