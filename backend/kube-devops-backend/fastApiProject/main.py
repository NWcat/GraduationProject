# app/main.py
from fastapi import FastAPI, Request, HTTPException
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from pydantic import ValidationError
import time
import uuid
from config import settings

from db.sqlite import init_db
from routers import (
    logs, prom, alerts, data, overview, tools, tools_kubectl,
    nodes, workloads, tenants, users, auth, namespaces, monitor, ai, ops,ops_config,clusters
)
from services.ops.scheduler import start_healer, stop_healer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # === startup ===
    init_db()
    auth.seed_admin()
    start_healer()
    yield
    # === shutdown ===
    stop_healer()


app = FastAPI(
    title="Monitoring API",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    start = time.time()
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.time() - start) * 1000)
        print(f"{request.method} {request.url.path} 500 {duration_ms}ms request_id={request_id}")
        raise
    duration_ms = int((time.time() - start) * 1000)
    response.headers["X-Request-Id"] = request_id
    print(f"{request.method} {request.url.path} {response.status_code} {duration_ms}ms request_id={request_id}")
    return response

def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _generic_detail(status_code: int) -> str:
    if status_code == 400:
        return "参数错误"
    if status_code == 401:
        return "未授权"
    if status_code == 403:
        return "无权限"
    if status_code == 404:
        return "资源不存在"
    if status_code == 409:
        return "业务冲突"
    if status_code >= 500:
        return "服务器内部错误"
    return "请求失败"


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else ""
    if not detail or not _has_chinese(detail):
        detail = _generic_detail(exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "参数错误"})


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(status_code=400, content={"detail": "参数错误"})


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": "参数错误"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})


# 注册路由
app.include_router(logs.router, prefix="/api")
app.include_router(prom.router)
app.include_router(alerts.router)
app.include_router(data.router)
app.include_router(overview.router)
app.include_router(tools.router)
app.include_router(tools_kubectl.router)
app.include_router(nodes.router)
app.include_router(workloads.router)
app.include_router(tenants.router)
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(namespaces.router)
app.include_router(monitor.router)
app.include_router(ai.router)
app.include_router(ops.router)
app.include_router(ops_config.router)
app.include_router(clusters.router)

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
