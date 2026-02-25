# services/ops/runtime_config.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Literal

from config import settings
from db.utils.sqlite import get_conn, q

# ✅ 前端 secret 展示/提交占位符（表示“不改”）
SECRET_PLACEHOLDER = "********"


# ---------------------------
# low-level: ops_config table
# ---------------------------

def _get_config(k: str) -> Optional[str]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT v FROM ops_config WHERE k=?", (k,))
        row = cur.fetchone()
        return None if not row else str(row["v"])
    finally:
        conn.close()


def _set_config(k: str, v: str) -> None:
    conn = get_conn()
    try:
        now = int(time.time())
        q(
            conn,
            """
            INSERT INTO ops_config(k, v, updated_ts)
            VALUES(?, ?, ?)
            ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_ts=excluded.updated_ts
            """,
            (k, str(v), now),
        )
        conn.commit()
    finally:
        conn.close()


def _del_config(k: str) -> None:
    conn = get_conn()
    try:
        q(conn, "DELETE FROM ops_config WHERE k=?", (k,))
        conn.commit()
    finally:
        conn.close()


def _list_configs() -> Dict[str, str]:
    conn = get_conn()
    try:
        cur = q(conn, "SELECT k, v FROM ops_config ORDER BY k ASC", ())
        rows = cur.fetchall()
        out: Dict[str, str] = {}
        for r in rows:
            out[str(r["k"])] = str(r["v"])
        return out
    finally:
        conn.close()


# ---------------------------
# parse helpers
# ---------------------------

def _to_bool(v: Optional[str], default: bool = False) -> bool:
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _to_int(v: Optional[str], default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _to_float(v: Optional[str], default: float = 0.0) -> float:
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _to_str(v: Optional[str], default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def _mask_secret(_: str) -> str:
    """
    ✅ 不泄露长度：统一固定占位符
    - 后端永远不把 secret 明文返回给前端
    """
    return SECRET_PLACEHOLDER


# ---------------------------
# Config Spec (whitelist)
# ---------------------------

ConfigType = Literal["str", "int", "bool", "float"]


@dataclass(frozen=True)
class ConfigSpec:
    key: str
    typ: ConfigType
    desc: str
    secret: bool = False
    # validate
    min_i: Optional[int] = None
    max_i: Optional[int] = None
    min_f: Optional[float] = None
    max_f: Optional[float] = None
    choices: Optional[List[str]] = None
    example: str = ""

    def parse(self, raw: Optional[str], default: Any) -> Any:
        if self.typ == "bool":
            return _to_bool(raw, default=bool(default))

        if self.typ == "int":
            try:
                safe_default = int(default)
            except Exception:
                safe_default = 0
            v = _to_int(raw, default=safe_default)
            if self.min_i is not None and v < self.min_i:
                v = self.min_i
            if self.max_i is not None and v > self.max_i:
                v = self.max_i
            return v

        if self.typ == "float":
            try:
                safe_default = float(default)
            except Exception:
                safe_default = 0.0
            v = _to_float(raw, default=safe_default)
            if self.min_f is not None and v < self.min_f:
                v = self.min_f
            if self.max_f is not None and v > self.max_f:
                v = self.max_f
            return v

        # str
        s = _to_str(raw, default=str(default))
        if self.choices and s and (s not in self.choices):
            # 不在可选值内就回落默认
            return default
        return s


# ✅ 只允许前端覆盖这些 key（白名单）
SPECS: Dict[str, ConfigSpec] = {
    # ---- kube ----
    "KUBE_MODE": ConfigSpec(
        key="KUBE_MODE",
        typ="str",
        desc="K8s 连接模式：auto/kubeconfig/incluster",
        choices=["auto", "kubeconfig", "incluster"],
        example="auto",
    ),
    "KUBECONFIG_PATH": ConfigSpec(
        key="KUBECONFIG_PATH",
        typ="str",
        desc="kubeconfig 文件路径（本机/容器内路径）",
        example="D:/xxx/.kube/config",
    ),
    "KUBECTL_BIN": ConfigSpec(
        key="KUBECTL_BIN",
        typ="str",
        desc="kubectl 可执行文件路径（本机/容器内路径）",
        example="D:/xxx/kubectl.exe",
    ),

    # ---- observability ----
    "PROMETHEUS_BASE": ConfigSpec(
        key="PROMETHEUS_BASE",
        typ="str",
        desc="Prometheus HTTP API base（建议带 /api/v1）",
        example="http://192.168.100.10:30900/api/v1",
    ),
    "LOKI_BASE": ConfigSpec(
        key="LOKI_BASE",
        typ="str",
        desc="Loki HTTP API base（建议带 /loki/api/v1）",
        example="http://192.168.100.10:30356/loki/api/v1",
    ),
    "ALERTMANAGER_BASE": ConfigSpec(
        key="ALERTMANAGER_BASE",
        typ="str",
        desc="Alertmanager API base（建议带 /api/v2）",
        example="http://192.168.100.10:31336/api/v2",
    ),
    "GRAFANA_BASE": ConfigSpec(
        key="GRAFANA_BASE",
        typ="str",
        desc="Grafana base url",
        example="http://192.168.100.10:3000",
    ),
    "PROMQL_FREE_ENABLED": ConfigSpec(
        key="PROMQL_FREE_ENABLED",
        typ="bool",
        desc="PromQL允许自由查询",
        example="0",
    ),
    "FEISHU_WEBHOOK_URL": ConfigSpec(
        key="FEISHU_WEBHOOK_URL",
        typ="str",
        desc="Feishu webhook url (platform alert push)",
        secret=True,
        example="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
    ),
    "ALERTS_PAGE_URL": ConfigSpec(
        key="ALERTS_PAGE_URL",
        typ="str",
        desc="Platform alert center url",
        example="http://localhost:5173/alerts",
    ),

    # ---- LLM (secret) ----
    "DEEPSEEK_API_KEY": ConfigSpec(
        key="DEEPSEEK_API_KEY",
        typ="str",
        desc="DeepSeek API Key（只允许后端存储；返回前端会脱敏）",
        secret=True,
        example="sk-xxxxxxxxxxxxxxxx",
    ),
    "DEEPSEEK_BASE_URL": ConfigSpec(
        key="DEEPSEEK_BASE_URL",
        typ="str",
        desc="DeepSeek Base URL",
        example="https://api.deepseek.com",
    ),
    "DEEPSEEK_MODEL": ConfigSpec(
        key="DEEPSEEK_MODEL",
        typ="str",
        desc="DeepSeek 模型名",
        example="deepseek-chat",
    ),
    "DEEPSEEK_TIMEOUT": ConfigSpec(
        key="DEEPSEEK_TIMEOUT",
        typ="int",
        desc="DeepSeek 请求超时（秒）",
        min_i=3,
        max_i=120,
        example="30",
    ),

    # ---- AI thresholds ----
    "AUTO_POD_CPU_THRESHOLD_RATIO": ConfigSpec(
        key="AUTO_POD_CPU_THRESHOLD_RATIO",
        typ="float",
        desc="Pod CPU observe threshold ratio",
        min_f=0.1,
        max_f=1.2,
        example="0.8",
    ),
    "AUTO_POD_CPU_HIGH_THRESHOLD_RATIO": ConfigSpec(
        key="AUTO_POD_CPU_HIGH_THRESHOLD_RATIO",
        typ="float",
        desc="Pod CPU trigger threshold ratio",
        min_f=0.1,
        max_f=1.2,
        example="0.9",
    ),
    "AUTO_POD_CPU_SUSTAIN_MINUTES": ConfigSpec(
        key="AUTO_POD_CPU_SUSTAIN_MINUTES",
        typ="int",
        desc="Pod CPU sustain minutes",
        min_i=1,
        max_i=120,
        example="10",
    ),

    # ---- AI execute safety ----
    "AI_EXECUTE_COOLDOWN_MINUTES": ConfigSpec(
        key="AI_EXECUTE_COOLDOWN_MINUTES",
        typ="int",
        desc="AI execute cooldown minutes (same object/action_type)",
        min_i=1,
        max_i=1440,
        example="10",
    ),
    "AI_EXECUTE_DAILY_LIMIT": ConfigSpec(
        key="AI_EXECUTE_DAILY_LIMIT",
        typ="int",
        desc="AI execute daily limit (global)",
        min_i=1,
        max_i=1000,
        example="20",
    ),
    "AI_EXECUTE_CONFIRM_TEXT": ConfigSpec(
        key="AI_EXECUTE_CONFIRM_TEXT",
        typ="str",
        desc="AI execute confirm text",
        example="EXECUTE",
    ),

    # ---- AI evolution ----
    "AI_EVOLUTION_ENABLED": ConfigSpec(
        key="AI_EVOLUTION_ENABLED",
        typ="bool",
        desc="规则引擎自我进化开关",
        example="0",
    ),
    "AI_EVOLUTION_MIN_FEEDBACKS": ConfigSpec(
        key="AI_EVOLUTION_MIN_FEEDBACKS",
        typ="int",
        desc="启用进化最少反馈数",
        min_i=1,
        max_i=1000,
        example="3",
    ),
    "AI_EVOLUTION_MAX_DELTA": ConfigSpec(
        key="AI_EVOLUTION_MAX_DELTA",
        typ="float",
        desc="单次调整的最大幅度（ratio）",
        min_f=0.0,
        max_f=0.5,
        example="0.05",
    ),

    # ---- healer ----
    "HEAL_ENABLED": ConfigSpec(
        key="HEAL_ENABLED",
        typ="bool",
        desc="是否启用自愈循环",
        example="1",
    ),
    "HEAL_EXECUTE": ConfigSpec(
        key="HEAL_EXECUTE",
        typ="bool",
        desc="是否真执行（False=只 dry-run 写审计）",
        example="0",
    ),
    "HEAL_INTERVAL_SEC": ConfigSpec(
        key="HEAL_INTERVAL_SEC",
        typ="int",
        desc="自愈循环间隔（秒）",
        min_i=5,
        max_i=3600,
        example="30",
    ),
    "HEAL_MAX_PER_CYCLE": ConfigSpec(
        key="HEAL_MAX_PER_CYCLE",
        typ="int",
        desc="每轮最多执行多少个动作",
        min_i=1,
        max_i=50,
        example="2",
    ),
    "HEAL_COOLDOWN_SEC": ConfigSpec(
        key="HEAL_COOLDOWN_SEC",
        typ="int",
        desc="同类动作冷却（秒）",
        min_i=0,
        max_i=3600,
        example="60",
    ),
    "HEAL_DENY_NS": ConfigSpec(
        key="HEAL_DENY_NS",
        typ="str",
        desc="黑名单命名空间（逗号分隔，或 '.' 表示不过滤）",
        example="kube-system,monitoring",
    ),

    # ---- decay (你已打通) ----
    "HEAL_DECAY_ON_RECOVER": ConfigSpec(
        key="HEAL_DECAY_ON_RECOVER",
        typ="bool",
        desc="连续成功自愈后 fail_count 衰减",
        example="1",
    ),
    "HEAL_DECAY_STEP": ConfigSpec(
        key="HEAL_DECAY_STEP",
        typ="int",
        desc="每次衰减步长",
        min_i=1,
        max_i=10,
        example="1",
    ),
    # ---- inspect ----
    "INSPECT_ENABLE_PROM": ConfigSpec(
        key="INSPECT_ENABLE_PROM",
        typ="bool",
        desc="巡检是否启用 Prometheus 检查（关闭后 Prometheus 不可用也不影响巡检）",
        example="1",
    ),
}


def _settings_default(k: str) -> Any:
    # settings 里没有的 key，就默认空
    return getattr(settings, k, "")


def get_value(k: str) -> Tuple[Any, str]:
    """
    取“生效值”
    returns: (value, source) source in {"db", "env"}
    """
    spec = SPECS.get(k)
    if not spec:
        # 未加入白名单的不允许被 UI 管控（但内部如果想用也可以自己加到 SPECS）
        return _settings_default(k), "env"

    raw = _get_config(k)
    default = _settings_default(k)
    if raw is None:
        return spec.parse(None, default), "env"
    return spec.parse(raw, default), "db"


def get_public_items() -> List[Dict[str, Any]]:
    """
    给前端 Settings UI 用：
    - value：secret 永远不回显明文，只回 ******** 或空
    - default：同理（如果默认值本来就为空，则返回空）
    - has_value：告诉前端该值是否真实“已设置”
    - choices：给前端做下拉（可选）
    """
    db_all = _list_configs()
    items: List[Dict[str, Any]] = []

    for k, spec in SPECS.items():
        default = _settings_default(k)
        raw_db = db_all.get(k)  # 原始db字符串（用于判断 override/has_value）
        val, src = get_value(k)

        if spec.secret:
            # ✅ secret：db里真的有值 -> 展示 ********；否则展示空（避免误导）
            show_val = _mask_secret(str(val)) if (src == "db" and raw_db and str(raw_db).strip()) else ""
            show_default = _mask_secret(str(default)) if str(default or "").strip() else ""
            has_value = bool(raw_db and str(raw_db).strip()) if src == "db" else bool(str(default or "").strip())
        else:
            show_val = val
            show_default = default
            has_value = bool(str(val or "").strip())

        items.append(
            {
                "k": k,
                "type": spec.typ,
                "desc": spec.desc,
                "secret": spec.secret,
                "source": src,  # db/env
                "value": show_val,
                "default": show_default,
                "has_override": raw_db is not None,
                "has_value": has_value,
                "example": spec.example,
                "choices": spec.choices or [],
            }
        )

    return items


def set_overrides(pairs: Dict[str, Any]) -> Dict[str, Any]:
    """
    批量设置覆盖值：
    - 只允许 SPECS 白名单内的 key
    - v 为空字符串/None：删除覆盖 -> 回落 env 默认
    - ✅ secret 的 v == ******** ：认为用户没改 -> 跳过（不写 DB）
    """
    applied: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    for k, v in (pairs or {}).items():
        if k not in SPECS:
            skipped.append(k)
            continue

        spec = SPECS[k]
        raw_s = None if v is None else str(v)

        # ✅ secret 占位符：不改
        if spec.secret and raw_s is not None and raw_s.strip() == SECRET_PLACEHOLDER:
            skipped.append(f"{k}(unchanged)")
            continue

        # ✅ 空值：删除覆盖
        if raw_s is None or raw_s.strip() == "":
            _del_config(k)
            applied.append(f"{k}=<deleted>")
            continue

        # ✅ choices：明确报错（比“默默回落默认”更友好）
        if spec.typ == "str" and spec.choices:
            if raw_s not in spec.choices:
                errors.append(f"{k}: must be one of {spec.choices}")
                continue

        # 软校验（范围/类型），不通过会回落/裁剪
        default = _settings_default(k)
        _ = spec.parse(raw_s, default)

        # 写入 DB：存原始字符串（更直观）
        _set_config(k, raw_s)
        applied.append(k)

    return {"ok": len(errors) == 0, "applied": applied, "skipped": skipped, "errors": errors}


def delete_override(k: str) -> Dict[str, Any]:
    if k not in SPECS:
        return {"ok": False, "reason": "key not allowed"}
    _del_config(k)
    return {"ok": True, "deleted": k}


# ---------------------------
# 你现有的衰减配置接口：保留兼容
# ---------------------------

K_DECAY_ON_RECOVER = "HEAL_DECAY_ON_RECOVER"
K_DECAY_STEP = "HEAL_DECAY_STEP"


def get_heal_decay_config() -> Tuple[bool, int]:
    enabled, _ = get_value(K_DECAY_ON_RECOVER)
    step, _ = get_value(K_DECAY_STEP)
    # 这里保证类型
    return bool(enabled), int(step)


def set_heal_decay_config(enabled: bool, step: int = 1) -> None:
    step = int(step)
    if step < 1:
        step = 1
    if step > 10:
        step = 10
    _set_config(K_DECAY_ON_RECOVER, "1" if bool(enabled) else "0")
    _set_config(K_DECAY_STEP, str(step))
