from __future__ import annotations

import importlib
import os
from typing import Any

from services.ai.schemas import SuggestionsResp

__path__ = [os.path.join(os.path.dirname(__file__), "rules")]

_pkg = importlib.import_module(__name__ + ".__init__")
RuleContext = _pkg.RuleContext
run_rules = _pkg.run_rules
list_rules = _pkg.list_rules
register_rule = _pkg.register_rule


def generate_node_cpu_suggestions(
    node: str,
    forecast: Any,
    threshold: float = 85.0,
    sustain_minutes: int = 15,
) -> SuggestionsResp:
    ctx = RuleContext(
        target="node_cpu",
        key=node,
        node=node,
        forecast=forecast,
        threshold=threshold,
        sustain_minutes=sustain_minutes,
    )
    meta = getattr(forecast, "meta", None) or {}
    return SuggestionsResp(target="node_cpu", key=node, suggestions=run_rules(ctx), meta=meta)


def generate_node_mem_suggestions(
    node: str,
    forecast: Any,
    threshold: float = 85.0,
    sustain_minutes: int = 15,
) -> SuggestionsResp:
    ctx = RuleContext(
        target="node_mem",
        key=node,
        node=node,
        forecast=forecast,
        threshold=threshold,
        sustain_minutes=sustain_minutes,
    )
    meta = getattr(forecast, "meta", None) or {}
    return SuggestionsResp(target="node_mem", key=node, suggestions=run_rules(ctx), meta=meta)


def generate_pod_cpu_suggestions(
    namespace: str,
    pod: str,
    forecast: Any,
    threshold_ratio: float = 0.80,
    high_threshold_ratio: float = 0.90,
    sustain_minutes: int = 10,
    scale_policy: str = "stair",
    safe_low: float = 0.6,
    safe_high: float = 0.7,
) -> SuggestionsResp:
    key = f"{namespace}/{pod}"
    ctx = RuleContext(
        target="pod_cpu",
        key=key,
        namespace=namespace,
        pod=pod,
        forecast=forecast,
        threshold_ratio=threshold_ratio,
        high_threshold_ratio=high_threshold_ratio,
        sustain_minutes=sustain_minutes,
        scale_policy=scale_policy,
        safe_low=safe_low,
        safe_high=safe_high,
    )
    meta = getattr(forecast, "meta", None) or {}
    return SuggestionsResp(target="pod_cpu", key=key, suggestions=run_rules(ctx), meta=meta)
