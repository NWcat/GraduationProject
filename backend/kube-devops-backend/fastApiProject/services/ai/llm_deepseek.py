# services/ai/llm_deepseek.py
from __future__ import annotations

from typing import Any, Dict, List
import requests

from config import settings
from services.ops.runtime_config import get_value  # ✅ DB override > settings/.env > default


def _cfg_str(key: str, default: str = "") -> str:
    v, _src = get_value(key)
    s = (str(v) if v is not None else "").strip()
    if s:
        return s
    return (str(default) if default is not None else "").strip()


def _cfg_int(key: str, default: int = 0) -> int:
    v, _src = get_value(key)
    try:
        return int(v)
    except Exception:
        try:
            return int(default)
        except Exception:
            return 0


class DeepSeekClient:
    """
    ✅ 方案B：读取配置时动态走 runtime_config.get_value()
    生效优先级：DB override（前端） > settings/.env > default
    """

    def __init__(self) -> None:
        # 保持轻量：不在 __init__ 固定配置，避免 DB 更新后不生效
        pass

    def _api_key(self) -> str:
        return _cfg_str("DEEPSEEK_API_KEY", str(getattr(settings, "DEEPSEEK_API_KEY", "") or "")).strip()

    def _base_url(self) -> str:
        u = _cfg_str("DEEPSEEK_BASE_URL", str(getattr(settings, "DEEPSEEK_BASE_URL", "") or "")).strip()
        return u.rstrip("/")

    def _model(self) -> str:
        return _cfg_str("DEEPSEEK_MODEL", str(getattr(settings, "DEEPSEEK_MODEL", "") or "")).strip()

    def _timeout(self) -> int:
        # 兜底 30（也可沿用你 settings 默认）
        return _cfg_int("DEEPSEEK_TIMEOUT", int(getattr(settings, "DEEPSEEK_TIMEOUT", 30) or 30))

    def enabled(self) -> bool:
        return bool(self._api_key() and self._base_url())

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        # ✅ 每次调用都取最新配置：确保“前端写 DB 后立即覆盖生效”
        api_key = self._api_key()
        base_url = self._base_url()
        model = self._model()
        timeout = self._timeout()

        if not (api_key and base_url):
            return "（未配置 DeepSeek：请设置 DEEPSEEK_API_KEY 与 DEEPSEEK_BASE_URL）"

        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        return str(data["choices"][0]["message"]["content"]).strip()
