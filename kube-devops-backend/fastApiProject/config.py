# fastApiProject/config.py
from typing import List, Literal, Optional
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

    CORS_ALLOW_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @property
    def prometheus_url(self) -> str:
        return self.PROMETHEUS_BASE.rstrip("/")

settings = Settings()
