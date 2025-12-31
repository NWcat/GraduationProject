import requests
from config import settings

ALERT_BASE = settings.ALERTMANAGER_BASE

def list_alerts():
    resp = requests.get(f"{ALERT_BASE}/alerts")
    resp.raise_for_status()
    return resp.json()
