from __future__ import annotations

import asyncio
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.repos import router as repos_router
from app.api.routers.github import router as github_router
from app.api.routers.gitlab import router as gitlab_router
from app.api.routers.jenkins import router as jenkins_router
from app.api.routers.azure import router as azure_router
from app.api.routers.logs import router as logs_router, tail_audit_log_websocket
from app.api.routers.config import router as config_router
from app.api.routers.analysis import router as analysis_router, stream_analysis_websocket
from app.api.routers.auth import router as auth_router
from app.api.routers.admin.credentials import router as admin_credentials_router
from app.api.routers.admin.llm import router as admin_llm_router
from app.api.routers.admin.slack import router as admin_slack_router
from app.api.routers.admin.agent_settings import router as admin_settings_router
from app.api.routers.admin.users import router as admin_users_router
from app.api.routers.users import router as users_router
from fastapi import Depends
from app.auth.dependencies import require_viewer_or_above, require_admin, get_current_user_ws
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.rate_limit import limiter

# Global event loop reference for background threads to broadcast
_main_loop: asyncio.AbstractEventLoop | None = None


class ConnectionManager:
    """Manages active WebSocket connections for real-time broadcasts."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


monitor_manager = ConnectionManager()


def broadcast_monitor_event(event: dict):
    """Trigger a broadcast from background monitor threads."""
    global _main_loop
    if _main_loop and monitor_manager.active_connections:
        asyncio.run_coroutine_threadsafe(
            monitor_manager.broadcast(json.dumps(event)),
            _main_loop
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    logging.info("FastAPI backend started, event loop captured.")
    
    # Start dashboard background monitors
    from app.api.monitors import start_dashboard_monitors
    start_dashboard_monitors(broadcast_monitor_event, _main_loop)
    logging.info("Dashboard monitors initialized.")
    yield


import time
import traceback
from fastapi.responses import JSONResponse

start_time = time.time()

app = FastAPI(title="DevOps AI Agent API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logging.error(f"Global Exception caught: {exc}\n{traceback.format_exc()}")
    # Avoid leaking internal stack trace details
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An unexpected internal server error occurred."
        }
    )

@app.get("/api/health", tags=["system"])
async def health_check():
    from app.config import settings
    llm_ok = False
    if settings.llm_provider == "gemini":
        llm_ok = bool(settings.google_api_key)
    else:
        llm_ok = True
        
    return {
        "status": "healthy",
        "version": "1.0.0",
        "llm_provider": settings.llm_provider,
        "model": settings.google_model if settings.llm_provider == "gemini" else "default",
        "llm_configured": llm_ok,
        "uptime_seconds": int(time.time() - start_time)
    }


# CORS configuration
from app.config import settings

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
if not origins:
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST API Routers
app.include_router(repos_router, prefix="/api/repos", tags=["repos"], dependencies=[Depends(require_viewer_or_above)])
app.include_router(github_router, prefix="/api/github", tags=["github"], dependencies=[Depends(require_viewer_or_above)])
app.include_router(gitlab_router, prefix="/api/gitlab", tags=["gitlab"], dependencies=[Depends(require_viewer_or_above)])
app.include_router(jenkins_router, prefix="/api/jenkins", tags=["jenkins"], dependencies=[Depends(require_viewer_or_above)])
app.include_router(azure_router, prefix="/api/azure", tags=["azure"], dependencies=[Depends(require_viewer_or_above)])
app.include_router(logs_router, prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_viewer_or_above)])
app.include_router(config_router, prefix="/api/config", tags=["config"], dependencies=[Depends(require_viewer_or_above)])
app.include_router(analysis_router, prefix="/api/analysis", tags=["analysis"], dependencies=[Depends(require_viewer_or_above)])

# Authentication & Onboarding
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# Current User Profile
app.include_router(users_router, prefix="/api/users", tags=["users"], dependencies=[Depends(require_viewer_or_above)])

# Admin Portal Configuration (Owner/Admin roles)
app.include_router(admin_credentials_router, prefix="/api/admin/credentials", tags=["admin-credentials"], dependencies=[Depends(require_admin)])
app.include_router(admin_llm_router, prefix="/api/admin/llm", tags=["admin-llm"], dependencies=[Depends(require_admin)])
app.include_router(admin_slack_router, prefix="/api/admin/slack", tags=["admin-slack"], dependencies=[Depends(require_admin)])
app.include_router(admin_settings_router, prefix="/api/admin/settings", tags=["admin-settings"], dependencies=[Depends(require_admin)])
app.include_router(admin_users_router, prefix="/api/admin/users", tags=["admin-users"], dependencies=[Depends(require_admin)])


# WebSockets
@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    user = await get_current_user_ws(websocket)
    if not user:
        return
    await tail_audit_log_websocket(websocket)


@app.websocket("/ws/analysis/{analysis_id}")
async def ws_analysis(websocket: WebSocket, analysis_id: str):
    user = await get_current_user_ws(websocket)
    if not user:
        return
    await stream_analysis_websocket(websocket, analysis_id, user["org_id"])


@app.websocket("/ws/monitors")
async def ws_monitors(websocket: WebSocket):
    user = await get_current_user_ws(websocket)
    if not user:
        return
    await monitor_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        monitor_manager.disconnect(websocket)
    except Exception:
        monitor_manager.disconnect(websocket)
