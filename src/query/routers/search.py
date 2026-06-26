from typing import Annotated

from fastapi import APIRouter, Query

from src.query.dependencies import PaginationDep, RepositoryDep
from src.query.schemas import SearchHit

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[SearchHit], summary="Keyword search over chunks")
async def search(
    repo: RepositoryDep,
    pagination: PaginationDep,
    term: Annotated[str, Query(min_length=2, description="Substring to find in chunk text")],
):
    """Naive case-insensitive substring search. NOT semantic — that arrives in Week 8."""
    return await repo.search_chunks(term, pagination.limit, pagination.offset)