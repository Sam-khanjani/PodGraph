from typing import Annotated

from fastapi import APIRouter, Query

from src.query.dependencies import PaginationDep, RepositoryDep
from src.query.schemas import ConceptCategory, ConceptDetailOut, ConceptSummary

router = APIRouter(prefix="/concepts", tags=["concepts"])


@router.get("", response_model=list[ConceptSummary], summary="List concepts")
async def list_concepts(
    repo: RepositoryDep,
    pagination: PaginationDep,
    category: Annotated[ConceptCategory | None, Query(description="Filter by category")] = None,
):
    cat = category.value if category else None
    return await repo.list_concepts(cat, pagination.limit, pagination.offset)


@router.get(
    "/{name}",
    response_model=ConceptDetailOut,
    summary="What different shows say about a concept (the graph-power view)",
    responses={404: {"description": "Concept not found"}},
)
async def get_concept(name: str, repo: RepositoryDep):
    """Cross-podcast synthesis for one concept.

    Names with spaces must be URL-encoded, e.g. `/concepts/Circadian%20Rhythm`.
    Matching is case-insensitive.
    """
    return await repo.get_concept(name)