# routers/users.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.users.service import reset_password, toggle_user

router = APIRouter(prefix="/api/users", tags=["users"])

class ResetPwdIn(BaseModel):
    username: str

@router.post("/reset-password")
def api_reset_pwd(payload: ResetPwdIn):
    try:
        otp = reset_password(payload.username.strip())
        return {"ok": True, "oneTimePassword": otp}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ToggleIn(BaseModel):
    username: str

@router.post("/toggle")
def api_toggle_user(payload: ToggleIn):
    try:
        st = toggle_user(payload.username.strip())
        return {"ok": True, "status": st}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))