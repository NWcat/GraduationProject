from fastapi import APIRouter, Request
from services.alert_client import list_alerts

router = APIRouter(prefix="/alerts", tags=["Alerts"])

@router.get("/list")
def get_alerts():
    return {
        "status": "success",
        "data": list_alerts()
    }

@router.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("收到告警:", data)
    return {"status": "ok"}
