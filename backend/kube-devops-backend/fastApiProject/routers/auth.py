from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.users.service import ensure_user, verify_user_password, update_user_password
from services.auth.service import create_access_token, decode_token
from fastapi import Header
router = APIRouter()

# 启动时调用：如果库里没有 admin 就创建
def seed_admin():
    # 你想改密码就改这里（后面再做“首次强制改密”）
    ensure_user("admin", "admin123", must_change=True)

class LoginReq(BaseModel):
    username: str
    password: str

class LoginResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class ChangePwdReq(BaseModel):
    oldPassword: str
    newPassword: str

class ChangePwdResp(BaseModel):
    ok: bool = True
    access_token: str
    token_type: str = "bearer"
    user: dict

@router.post("/auth/login", response_model=LoginResp)
def login(req: LoginReq):
    u = (req.username or "").strip()
    p = req.password or ""
    if not u or not p:
        raise HTTPException(status_code=400, detail="username and password required")

    try:
        user = verify_user_password(u, p)
    except ValueError as e:
        msg = str(e)
        if msg == "user disabled":
            raise HTTPException(status_code=403, detail="user disabled")
        raise HTTPException(status_code=401, detail="invalid username or password")

    token = create_access_token(subject=u, extra={"must_change": user["must_change"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "status": user["status"],
            "mustChange": user["must_change"],
        },
    }

def get_current_username(authorization: str = Header(default="")) -> str:
    # 期望：Bearer xxx
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="invalid token")
        return sub
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")

@router.post("/auth/change-password", response_model=ChangePwdResp)
def change_password(req: ChangePwdReq, username: str = Depends(get_current_username)):
    oldp = req.oldPassword or ""
    newp = (req.newPassword or "").strip()
    if not oldp or not newp:
        raise HTTPException(status_code=400, detail="oldPassword and newPassword required")

    try:
        updated = update_user_password(username, oldp, newp)
    except ValueError as e:
        msg = str(e)
        if msg in ("invalid old password",):
            raise HTTPException(status_code=400, detail="old password incorrect")
        if msg in ("password too short",):
            raise HTTPException(status_code=400, detail="password too short")
        if msg == "user disabled":
            raise HTTPException(status_code=403, detail="user disabled")
        raise HTTPException(status_code=400, detail=msg)

    # ✅ 改密成功后签发新 token（must_change 必须变 false）
    token = create_access_token(subject=username, extra={"must_change": False})
    return {
        "ok": True,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": updated["username"],
            "status": updated["status"],
            "mustChange": False,
        },
    }