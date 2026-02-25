from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional

import requests

from config import settings
from services.ops.runtime_config import get_value
from db.alerts.repo import update_push_status


_executor = threading.BoundedSemaphore(8)


def _cfg_str(key: str, default: str = "") -> str:
    v, _src = get_value(key)
    s = str(v or "").strip()
    return s if s else str(default or "")


def _feishu_webhook_url() -> str:
    return _cfg_str("FEISHU_WEBHOOK_URL", str(getattr(settings, "FEISHU_WEBHOOK_URL", "") or ""))


def _alerts_page_url() -> str:
    return _cfg_str("ALERTS_PAGE_URL", str(getattr(settings, "ALERTS_PAGE_URL", "") or ""))


def _build_card(alert: Dict[str, Any]) -> Dict[str, Any]:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    title = str(labels.get("alertname") or annotations.get("summary") or "Platform Alert")
    severity = str(labels.get("severity") or "warning")
    resource = str(labels.get("namespace") or "") + "/" + str(labels.get("pod") or labels.get("deployment") or "")
    starts_at = str(alert.get("starts_at") or "")
    status = str(alert.get("status") or "")
    source = str(alert.get("source") or "")
    url = _alerts_page_url()

    fields = [
        {"is_short": True, "text": f"**Level**\n{severity}"},
        {"is_short": True, "text": f"**Status**\n{status}"},
        {"is_short": True, "text": f"**Source**\n{source}"},
        {"is_short": False, "text": f"**Resource**\n{resource or '-'}"},
        {"is_short": False, "text": f"**Starts**\n{starts_at or '-'}"},
    ]
    if url:
        fields.append({"is_short": False, "text": f"**Link**\n{url}"})

    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [{"tag": "div", "fields": fields}],
        },
    }


def push_alert_async(alert: Dict[str, Any]) -> None:
    url = _feishu_webhook_url()
    fingerprint = str(alert.get("fingerprint") or "")
    if not url or not fingerprint:
        return

    def _runner() -> None:
        if not _executor.acquire(blocking=False):
            return
        try:
            payload = _build_card(alert)
            resp = requests.post(url, json=payload, timeout=6)
            ok = 200 <= resp.status_code < 300
            if ok:
                update_push_status(fingerprint=fingerprint, status="ok", error="")
            else:
                update_push_status(
                    fingerprint=fingerprint,
                    status="failed",
                    error=f"status={resp.status_code} body={resp.text[:200]}",
                )
        except Exception as e:
            update_push_status(fingerprint=fingerprint, status="failed", error=str(e))
        finally:
            _executor.release()

    t = threading.Thread(target=_runner, name="feishu-push", daemon=True)
    t.start()

