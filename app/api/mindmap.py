"""Mind map query API route."""
from fastapi import APIRouter

from app.services.mind_map_service import MindMapService

router = APIRouter(prefix="/mindmap", tags=["mindmap"])


@router.get("")
def get_mindmap(workspace_id: str):
    service = MindMapService(workspace_id)
    return service.get_map_state()
