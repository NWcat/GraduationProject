from __future__ import annotations

from typing import List

from .registry import register_rule, list_rules
from .types import RuleContext, RuleResult

from . import node_cpu  # noqa: F401
from . import node_mem  # noqa: F401
from . import pod_cpu  # noqa: F401


def run_rules(ctx: RuleContext) -> List[RuleResult]:
    out: List[RuleResult] = []
    for spec in list_rules():
        if spec.target and spec.target != ctx.target:
            continue
        res = spec.func(ctx)
        if res is not None:
            out.append(res)
    return out
