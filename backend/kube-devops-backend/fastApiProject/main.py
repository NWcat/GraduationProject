# app/main.py
from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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
