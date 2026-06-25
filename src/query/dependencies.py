from collections.abc import AsyncIterator
from typing import Annotated
from fastapi import Depends, Query
from neo4j import AsyncSession
from src.query.db import AsyncNeo4j
from src.query.repository import GraphRepository


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped Neo4j session; the `async with` guarantees cleanup."""
    driver = AsyncNeo4j.driver()
    async with driver.session() as session:
        yield session


async def get_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GraphRepository:
    return GraphRepository(session)


# A reusable typed alias — endpoints just write `repo: RepositoryDep`.
RepositoryDep = Annotated[GraphRepository, Depends(get_repository)]


class Pagination:
    """Bundles validated pagination query params (?limit=&offset=)."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=100, description="Max items to return")] = 20,
        offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends(Pagination)]