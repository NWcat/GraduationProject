# fastApiProject/config.py
from typing import List, Literal, Optional

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_ENV: Literal["dev", "test", "prod"] = "dev"
    APP_DEBUG: bool = True
    HTTP_TIMEOUT_SECONDS: int = 10

    # ✅ auto / kubeconfig / incluster
    KUBE_MODE: Literal["auto", "kubeconfig", "incluster"] = "auto"
    KUBECONFIG_PATH: Optional[str] = None
    KUBECTL_BIN: str | None = None

    PROMETHEUS_BASE: str = "http://localhost:9090"
    LOKI_BASE: str = "http://localhost:3100"
    ALERTMANAGER_BASE: str = "http://localhost:9093"
    GRAFANA_BASE: str = "http://localhost:3000"

    # ===== AI / LLM =====
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: AnyHttpUrl | None = None
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TIMEOUT: int = 30

    # ===== OPS / Healer =====
    HEAL_ENABLED: bool = True
    # False=只 dry-run 写审计；True=真执行 delete pod
    HEAL_EXECUTE: bool = False

    HEAL_INTERVAL_SEC: int = 60
    HEAL_MAX_PER_CYCLE: int = 3
    HEAL_COOLDOWN_SEC: int = 300

    # 逗号分隔字符串："" 表示不限制
    # HEAL_ALLOW_NS: str = ""
    HEAL_DENY_NS: str = "kube-system,kube-public,kube-node-lease,monitoring,logging"

    # 只处理哪些原因（逗号分隔）：CrashLoopBackOff,NotReady；"" 表示都处理
    HEAL_ONLY_REASONS: str = ""

    # ===== OPS / Auto Ops（自动联动建议执行）=====
    AUTO_OPS_ENABLED: bool = False
    AUTO_OPS_EXECUTE: bool = False
    AUTO_OPS_COOLDOWN_SEC: int = 300
    AUTO_POD_CPU_THRESHOLD_RATIO: float = 0.80
    AUTO_POD_CPU_HIGH_THRESHOLD_RATIO: float = 0.90
    AUTO_POD_CPU_SUSTAIN_MINUTES: int = 10

    # ---- decay ----
    HEAL_DECAY_ON_RECOVER: bool = True  # 或 False，看你默认想不想开
    HEAL_DECAY_STEP: int = 1

    # ===== Inspect / 巡检 =====
    INSPECT_ENABLE_PROM: bool = True  # Prometheus 不可用时也不要让巡检整体失败：关闭即可

    CORS_ALLOW_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @property
    def prometheus_url(self) -> str:
        return self.PROMETHEUS_BASE.rstrip("/")

settings = Settings()
