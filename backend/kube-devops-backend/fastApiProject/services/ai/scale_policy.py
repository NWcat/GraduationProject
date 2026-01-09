# services/ai/scale_policy.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class LinearScaleResult:
    ok: bool
    reason: str = ""
    current_replicas: int = 0
    target_replicas: int = 0
    peak_ratio: float = 0.0
    safe_low: float = 0.6
    safe_high: float = 0.7
    est_ratio_after: float = 0.0
    scale_up: bool = False
    scale_down: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "current_replicas": self.current_replicas,
            "target_replicas": self.target_replicas,
            "peak_ratio": self.peak_ratio,
            "safe_low": self.safe_low,
            "safe_high": self.safe_high,
            "est_ratio_after": self.est_ratio_after,
            "scale_up": self.scale_up,
            "scale_down": self.scale_down,
        }


# =========================
# ✅ 资源调优策略（线性/阶梯）
# =========================
@dataclass
class ResourceTuneResult:
    ok: bool
    reason: str = ""
    # 当前值（可选：用于回显/审计，不强依赖）
    current_cpu_request_m: Optional[int] = None
    current_cpu_limit_m: Optional[int] = None
    current_mem_request_mb: Optional[int] = None
    current_mem_limit_mb: Optional[int] = None

    # 目标值（输出）
    target_cpu_request_m: Optional[int] = None
    target_cpu_limit_m: Optional[int] = None
    target_mem_request_mb: Optional[int] = None
    target_mem_limit_mb: Optional[int] = None

    # 依据
    peak_cpu_m: Optional[float] = None
    peak_mem_mb: Optional[float] = None
    peak_ratio_cpu: Optional[float] = None  # peak_cpu / limit_cpu
    peak_ratio_mem: Optional[float] = None  # peak_mem / limit_mem
    policy_used: str = "linear"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "current_cpu_request_m": self.current_cpu_request_m,
            "current_cpu_limit_m": self.current_cpu_limit_m,
            "current_mem_request_mb": self.current_mem_request_mb,
            "current_mem_limit_mb": self.current_mem_limit_mb,
            "target_cpu_request_m": self.target_cpu_request_m,
            "target_cpu_limit_m": self.target_cpu_limit_m,
            "target_mem_request_mb": self.target_mem_request_mb,
            "target_mem_limit_mb": self.target_mem_limit_mb,
            "peak_cpu_m": self.peak_cpu_m,
            "peak_mem_mb": self.peak_mem_mb,
            "peak_ratio_cpu": self.peak_ratio_cpu,
            "peak_ratio_mem": self.peak_ratio_mem,
            "policy_used": self.policy_used,
        }


def _clamp_int(v: int, lo: int, hi: int) -> int:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _to_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def _stair_factor(ratio: float) -> float:
    """
    阶梯倍率（用于资源调整）
    ratio 是 peak/limit（或 peak/request）一类占比，越高说明越需要上调资源。
    """
    try:
        r = float(ratio or 0.0)
    except Exception:
        r = 0.0

    if r < 0.9:
        return 1.0
    if r < 1.0:
        return 1.2
    if r < 1.2:
        return 1.5
    if r < 1.5:
        return 2.0
    return 2.5


def calc_resource_targets_linear(
    *,
    # 预测峰值（可只给 CPU 或只给 MEM）
    peak_cpu_m: Optional[float] = None,
    peak_mem_mb: Optional[float] = None,

    # 当前 limit/request（用于计算 ratio / 作为保底；可为 None）
    current_cpu_request_m: Optional[int] = None,
    current_cpu_limit_m: Optional[int] = None,
    current_mem_request_mb: Optional[int] = None,
    current_mem_limit_mb: Optional[int] = None,

    # 目标安全区间（比扩容类似）：把 peak/limit 拉回 safe_high 以下
    safe_low: float = 0.6,
    safe_high: float = 0.7,

    # 资源上下限（防止离谱）
    min_cpu_m: int = 10,
    max_cpu_m: int = 4000,
    min_mem_mb: int = 16,
    max_mem_mb: int = 32768,

    # request/limit 的关系：默认 request = limit * request_ratio
    request_ratio: float = 0.6,
) -> ResourceTuneResult:
    """
    线性资源调整核心假设：
    - 我们希望把预测峰值的利用率压到 safe_high 以下：
      peak / new_limit <= safe_high  => new_limit >= peak / safe_high

    产出：
    - target_*_limit = ceil(peak/safe_high)
    - target_*_request = ceil(target_limit * request_ratio)
    """
    sl = float(safe_low)
    sh = float(safe_high)
    if not (0 < sl < sh <= 1.5):
        return ResourceTuneResult(ok=False, reason="invalid safe_low/safe_high", policy_used="linear")

    rr = float(request_ratio)
    if not (0.05 <= rr <= 1.0):
        rr = 0.6

    out = ResourceTuneResult(
        ok=True,
        reason="computed",
        current_cpu_request_m=_to_int(current_cpu_request_m),
        current_cpu_limit_m=_to_int(current_cpu_limit_m),
        current_mem_request_mb=_to_int(current_mem_request_mb),
        current_mem_limit_mb=_to_int(current_mem_limit_mb),
        peak_cpu_m=float(peak_cpu_m) if peak_cpu_m is not None else None,
        peak_mem_mb=float(peak_mem_mb) if peak_mem_mb is not None else None,
        policy_used="linear",
    )

    # CPU
    if peak_cpu_m is not None and float(peak_cpu_m) > 0:
        # 如果当前 limit 为空，用 peak 作为参考，ratio 置 None 也行；这里尽量算出来
        if current_cpu_limit_m and current_cpu_limit_m > 0:
            out.peak_ratio_cpu = float(peak_cpu_m) / float(current_cpu_limit_m)

        need_limit = int(math.ceil(float(peak_cpu_m) / sh))
        need_limit = _clamp_int(need_limit, int(min_cpu_m), int(max_cpu_m))
        out.target_cpu_limit_m = need_limit

        need_req = int(math.ceil(float(need_limit) * rr))
        need_req = _clamp_int(need_req, int(min_cpu_m), int(max_cpu_m))
        out.target_cpu_request_m = need_req

    # MEM
    if peak_mem_mb is not None and float(peak_mem_mb) > 0:
        if current_mem_limit_mb and current_mem_limit_mb > 0:
            out.peak_ratio_mem = float(peak_mem_mb) / float(current_mem_limit_mb)

        need_limit = int(math.ceil(float(peak_mem_mb) / sh))
        need_limit = _clamp_int(need_limit, int(min_mem_mb), int(max_mem_mb))
        out.target_mem_limit_mb = need_limit

        need_req = int(math.ceil(float(need_limit) * rr))
        need_req = _clamp_int(need_req, int(min_mem_mb), int(max_mem_mb))
        out.target_mem_request_mb = need_req

    if out.target_cpu_limit_m is None and out.target_mem_limit_mb is None:
        out.ok = False
        out.reason = "no_peak_input"

    return out


def calc_resource_targets_stair(
    *,
    peak_cpu_m: Optional[float] = None,
    peak_mem_mb: Optional[float] = None,
    current_cpu_request_m: Optional[int] = None,
    current_cpu_limit_m: Optional[int] = None,
    current_mem_request_mb: Optional[int] = None,
    current_mem_limit_mb: Optional[int] = None,
    # 阶梯倍率基于 ratio：peak/current_limit（如果 current_limit 缺失，用 request）
    min_cpu_m: int = 10,
    max_cpu_m: int = 4000,
    min_mem_mb: int = 16,
    max_mem_mb: int = 32768,
    request_ratio: float = 0.6,
) -> ResourceTuneResult:
    """
    阶梯资源调整：
    - 用 ratio = peak / (current_limit or current_request)
    - 通过 _stair_factor(ratio) 得到倍率，对 current_limit 做乘法上调
    """
    rr = float(request_ratio)
    if not (0.05 <= rr <= 1.0):
        rr = 0.6

    out = ResourceTuneResult(
        ok=True,
        reason="computed",
        current_cpu_request_m=_to_int(current_cpu_request_m),
        current_cpu_limit_m=_to_int(current_cpu_limit_m),
        current_mem_request_mb=_to_int(current_mem_request_mb),
        current_mem_limit_mb=_to_int(current_mem_limit_mb),
        peak_cpu_m=float(peak_cpu_m) if peak_cpu_m is not None else None,
        peak_mem_mb=float(peak_mem_mb) if peak_mem_mb is not None else None,
        policy_used="stair",
    )

    # CPU
    if peak_cpu_m is not None and float(peak_cpu_m) > 0:
        base = None
        if current_cpu_limit_m and current_cpu_limit_m > 0:
            base = int(current_cpu_limit_m)
        elif current_cpu_request_m and current_cpu_request_m > 0:
            base = int(current_cpu_request_m)

        if base and base > 0:
            ratio = float(peak_cpu_m) / float(base)
            out.peak_ratio_cpu = ratio
            factor = _stair_factor(ratio)
            need_limit = int(math.ceil(float(base) * factor))
        else:
            # 没有 current：退化为“至少覆盖 peak”
            need_limit = int(math.ceil(float(peak_cpu_m)))

        need_limit = _clamp_int(need_limit, int(min_cpu_m), int(max_cpu_m))
        out.target_cpu_limit_m = need_limit

        need_req = int(math.ceil(float(need_limit) * rr))
        need_req = _clamp_int(need_req, int(min_cpu_m), int(max_cpu_m))
        out.target_cpu_request_m = need_req

    # MEM
    if peak_mem_mb is not None and float(peak_mem_mb) > 0:
        base = None
        if current_mem_limit_mb and current_mem_limit_mb > 0:
            base = int(current_mem_limit_mb)
        elif current_mem_request_mb and current_mem_request_mb > 0:
            base = int(current_mem_request_mb)

        if base and base > 0:
            ratio = float(peak_mem_mb) / float(base)
            out.peak_ratio_mem = ratio
            factor = _stair_factor(ratio)
            need_limit = int(math.ceil(float(base) * factor))
        else:
            need_limit = int(math.ceil(float(peak_mem_mb)))

        need_limit = _clamp_int(need_limit, int(min_mem_mb), int(max_mem_mb))
        out.target_mem_limit_mb = need_limit

        need_req = int(math.ceil(float(need_limit) * rr))
        need_req = _clamp_int(need_req, int(min_mem_mb), int(max_mem_mb))
        out.target_mem_request_mb = need_req

    if out.target_cpu_limit_m is None and out.target_mem_limit_mb is None:
        out.ok = False
        out.reason = "no_peak_input"

    return out


def calc_linear_target_replicas(
    *,
    current_replicas: int,
    peak_ratio: float,
    safe_low: float = 0.6,
    safe_high: float = 0.7,
    min_replicas: int = 1,
    max_replicas: int = 200,
    allow_scale_down: bool = False,
) -> LinearScaleResult:
    """
    线性比例扩容核心假设（对论文解释很友好）：
    - 总负载近似恒定，单 Pod 负载 ~ 1/replicas
    - 所以 ratio_after ~= peak_ratio * current_replicas / target_replicas

    目标：把预测峰值 ratio 拉回 [safe_low, safe_high] 区间。
    默认：只扩容不缩容（allow_scale_down=False），避免抖动/误降。
    """
    try:
        cr = int(current_replicas)
    except Exception:
        cr = 0

    if cr <= 0:
        return LinearScaleResult(ok=False, reason="current_replicas<=0", current_replicas=cr, peak_ratio=float(peak_ratio))

    pr = float(peak_ratio or 0.0)
    if pr <= 0:
        return LinearScaleResult(ok=False, reason="peak_ratio<=0", current_replicas=cr, peak_ratio=pr)

    sl = float(safe_low)
    sh = float(safe_high)
    if not (0 < sl < sh <= 1.5):
        return LinearScaleResult(ok=False, reason="invalid safe_low/safe_high", current_replicas=cr, peak_ratio=pr, safe_low=sl, safe_high=sh)

    # 如果已经在安全区间内：不动
    if sl <= pr <= sh:
        return LinearScaleResult(
            ok=True,
            reason="already_in_safe_band",
            current_replicas=cr,
            target_replicas=cr,
            peak_ratio=pr,
            safe_low=sl,
            safe_high=sh,
            est_ratio_after=pr,
        )

    # 扩容：把 ratio 压到 safe_high 以下
    # ratio_after = pr * cr / tr <= sh  => tr >= pr*cr/sh
    need = int(math.ceil((pr * cr) / sh))
    need = _clamp_int(need, min_replicas, max_replicas)

    # 默认不缩容
    if need < cr and not allow_scale_down:
        return LinearScaleResult(
            ok=True,
            reason="scale_down_blocked",
            current_replicas=cr,
            target_replicas=cr,
            peak_ratio=pr,
            safe_low=sl,
            safe_high=sh,
            est_ratio_after=pr,
            scale_down=False,
        )

    est = pr * cr / max(need, 1)

    return LinearScaleResult(
        ok=True,
        reason="computed",
        current_replicas=cr,
        target_replicas=need,
        peak_ratio=pr,
        safe_low=sl,
        safe_high=sh,
        est_ratio_after=float(est),
        scale_up=(need > cr),
        scale_down=(need < cr),
    )

