from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .types import RuleContext, RuleResult


@dataclass
class RuleSpec:
    name: str
    target: Optional[str]
    priority: int
    order: int
    func: Callable[[RuleContext], RuleResult]


RULES: List[RuleSpec] = []
_order_counter = 0


def register_rule(name: str, target: Optional[str] = None, priority: int = 100):
    def _decorator(fn: Callable[[RuleContext], RuleResult]):
        global _order_counter
        _order_counter += 1
        RULES.append(
            RuleSpec(
                name=str(name),
                target=str(target) if target is not None else None,
                priority=int(priority),
                order=int(_order_counter),
                func=fn,
            )
        )
        return fn

    return _decorator


def list_rules() -> List[RuleSpec]:
    return sorted(RULES, key=lambda r: (r.priority, r.order))
