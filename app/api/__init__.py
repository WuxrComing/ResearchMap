from app.api.settings import router as settings_router
from app.api.workspaces import router as workspaces_router
from app.api.workspace_settings import router as workspace_settings_router
from app.api.sessions import router as sessions_router
from app.api.chat import router as chat_router
from app.api.mindmap import router as mindmap_router

from fastapi import APIRouter

api_router = APIRouter(prefix="/api")
api_router.include_router(settings_router)
api_router.include_router(workspaces_router)
api_router.include_router(workspace_settings_router)
api_router.include_router(sessions_router)
api_router.include_router(chat_router)
api_router.include_router(mindmap_router)
