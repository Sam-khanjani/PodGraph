from fastapi import APIRouter

from src.query.dependencies import RepositoryDep
from src.query.schemas import EpisodeOut

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.get(
    "/{episode_id}",
    response_model=EpisodeOut,
    summary="Get one episode with its guests and chunks",
    responses={404: {"description": "Episode not found"}},
)
async def get_episode(episode_id: str, repo: RepositoryDep):
    return await repo.get_episode(episode_id)