#!/usr/bin/env python
"""
调试脚本：测试 CORS 是否正常工作
"""
import sys
sys.path.insert(0, '.')

from config import settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

print("=" * 60)
print("CORS 调试信息")
print("=" * 60)

# 1. 检查配置
print("\n1. 配置读取检查：")
print(f"   CORS_ALLOW_ORIGINS type: {type(settings.CORS_ALLOW_ORIGINS)}")
print(f"   CORS_ALLOW_ORIGINS value: {settings.CORS_ALLOW_ORIGINS}")
print(f"   Length: {len(settings.CORS_ALLOW_ORIGINS)}")
for i, origin in enumerate(settings.CORS_ALLOW_ORIGINS):
    print(f"   [{i}] {origin}")

# 2. 创建测试应用
print("\n2. 创建测试 FastAPI 应用：")
app = FastAPI()

# 添加 CORS 中间件 - 完全相同的配置
cors_origins = list(settings.CORS_ALLOW_ORIGINS)
print(f"   使用的 CORS 源：{cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 添加调试路由
@app.get("/debug/cors-config")
async def cors_config():
    return {
        "configured_origins": cors_origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }

@app.get("/debug/request-info")
async def request_info(request: Request):
    return {
        "client": str(request.client),
        "origin": request.headers.get("origin"),
        "referer": request.headers.get("referer"),
        "user_agent": request.headers.get("user-agent"),
        "headers": dict(request.headers),
    }

@app.options("/{path:path}")
async def cors_preflight(request: Request):
    """显式处理 CORS preflight"""
    origin = request.headers.get("origin")
    print(f"[PREFLIGHT] OPTIONS request from origin: {origin}")
    print(f"[PREFLIGHT] Configured origins: {cors_origins}")
    print(f"[PREFLIGHT] Origin in list: {origin in cors_origins}")

    response = JSONResponse({"ok": True})
    return response

@app.get("/test")
async def test(request: Request):
    origin = request.headers.get("origin")
    return {
        "status": "ok",
        "message": "如果看到这个，说明 CORS 预检通过",
        "origin": origin,
    }

# 4. 启动信息
print("\n3. 启动测试服务器：")
print("   服务器将在 http://0.0.0.0:8001 上运行（与主服务器不同端口以避免冲突）")
print("\n4. 浏览器中测试：")
print("   打开浏览器控制台，运行：")
print("""
   fetch('http://127.0.0.1:8001/test', {
     method: 'GET',
     credentials: 'include'
   }).then(r => r.json()).then(d => console.log('SUCCESS:', d))
     .catch(e => console.error('FAILED:', e))
   """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="debug")
