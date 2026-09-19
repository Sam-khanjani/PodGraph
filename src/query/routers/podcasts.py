from fastapi import APIRouter

from src.query.dependencies import RepositoryDep
from src.query.schemas import PodcastOut

router = APIRouter(prefix="/podcasts", tags=["podcasts"])


@router.get("", response_model=list[PodcastOut], summary="List all podcasts")
async def list_podcasts(repo: RepositoryDep):
    return await repo.list_podcasts()