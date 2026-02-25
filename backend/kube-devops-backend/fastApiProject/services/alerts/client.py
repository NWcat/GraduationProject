# services/alert_client.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests
from datetime import datetime, timezone

from config import settings
from services.ops.runtime_config import get_value  # ✅ DB override > settings/.env > default


def _cfg_str(key: str, default: str) -> str:
    v, _src = get_value(key)
    s = (str(v) if v is not None else "").strip()
    return s if s else str(default)


def _alert_base() -> str:
    # default: 从 settings 取（等价于 .env），再兜底 ""
    base = _cfg_str("ALERTMANAGER_BASE", str(getattr(settings, "ALERTMANAGER_BASE", "") or ""))
    return str(base).rstrip("/")


def _url(path: str) -> str:
    base = (_alert_base() or "").rstrip("/")
    if not base:
        return ""
    if path.startswith("/"):
        path = path[1:]
    return f"{base}/{path}"


def list_alerts() -> Any:
    url = _url("alerts")
    if not url:
        raise RuntimeError("ALERTMANAGER_BASE not set")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def push_alert(
    *,
    alertname: str,
    severity: str = "warning",
    labels: Optional[Dict[str, str]] = None,
    annotations: Optional[Dict[str, str]] = None,
) -> Any:
    url = _url("alerts")
    if not url:
        return {"ok": False, "skipped": True, "reason": "ALERTMANAGER_BASE not set"}

    lbs: Dict[str, str] = {"alertname": alertname, "severity": severity}
    if labels:
        for k, v in labels.items():
            if v is None:
                continue
            lbs[str(k)] = str(v)

    anns: Dict[str, str] = {}
    if annotations:
        for k, v in annotations.items():
            if v is None:
                continue
            anns[str(k)] = str(v)

    payload: List[Dict[str, Any]] = [
        {"labels": lbs, "annotations": anns, "startsAt": datetime.now(timezone.utc).isoformat()}
    ]

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return {"ok": True, "status_code": resp.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def push_test_alert(
    *,
    alertname: str,
    severity: str = "warning",
    namespace: str = "default",
    deployment: str = "",
    summary: str = "test alert",
    description: str = "test alert from backend",
    extra_labels: Optional[Dict[str, str]] = None,
) -> Any:
    labels = {"alertname": alertname, "severity": severity, "namespace": namespace}
    if deployment:
        labels["deployment"] = deployment
    if extra_labels:
        labels.update(extra_labels)

    payload: List[Dict[str, Any]] = [
        {
            "labels": labels,
            "annotations": {"summary": summary, "description": description},
            "startsAt": datetime.now(timezone.utc).isoformat(),
        }
    ]

    url = _url("alerts")
    if not url:
        raise RuntimeError("ALERTMANAGER_BASE not set")
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return {"ok": True, "status_code": resp.status_code}
