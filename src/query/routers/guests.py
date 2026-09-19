from fastapi import APIRouter

from src.query.dependencies import RepositoryDep
from src.query.schemas import GuestDetailOut

router = APIRouter(prefix="/guests", tags=["guests"])


@router.get(
    "/{name}",
    response_model=GuestDetailOut,
    summary="Guest detail with podcasts, episodes, and concepts",
    responses={404: {"description": "Guest not found"}},
)
async def get_guest(name: str, repo: RepositoryDep):
    return await repo.get_guest(name)