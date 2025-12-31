# app/main.py
from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from db.sqlite import init_db
from routers import logs, prom, alerts, data, overview, tools, tools_kubectl, nodes, workloads,tenants,users, auth,namespaces,monitor

app = FastAPI(title="Monitoring API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产可改成指定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
auth.seed_admin()
# 注册路由
app.include_router(logs.router,prefix="/api")
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
@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)