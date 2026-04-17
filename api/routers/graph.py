"""
Graph router: GET /api/v1/graph/{id}

Returns a depth-2 subgraph centered on the entity identified by id.
Most expensive endpoint — rate limited to 10/minute per IP.
Returns HTTP 408 on Neo4j query timeout (>30s).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from neo4j import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from dependencies import get_neo4j_session, get_privacy_filter
from middleware.privacy import PrivacyFilter
from models.graph import GraphResponse, PathResponse
from models.responses import APIResponse, ResponseMeta
from services.graph_service import get_subgraph
from services.path_service import get_shortest_path
from services.freshness_service import get_freshness, build_response_meta

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/graph/path", response_model=APIResponse[PathResponse])
@limiter.limit("10/minute")
async def graph_path(
    request: Request,
    from_id: str,
    to_id: str,
    session: AsyncSession = Depends(get_neo4j_session),
    privacy: PrivacyFilter = Depends(get_privacy_filter),
):
    """Shortest path between two entities (max 6 hops)."""
    try:
        path = await get_shortest_path(
            from_id=from_id, to_id=to_id, session=session, privacy=privacy
        )
    except Exception:
        raise HTTPException(status_code=408, detail="Path query timed out.")

    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No path found between {from_id} and {to_id}",
        )

    freshness = await get_freshness(session)
    return APIResponse(
        data=PathResponse(**path),
        meta=ResponseMeta(**build_response_meta(freshness)),
    )


@router.get("/graph/{id}", response_model=APIResponse[GraphResponse])
@limiter.limit("10/minute")
async def graph(
    request: Request,
    id: str,
    session: AsyncSession = Depends(get_neo4j_session),
    privacy: PrivacyFilter = Depends(get_privacy_filter),
):
    """
    Procurement network subgraph centered on any entity.

    - **id**: NIT, cedula, id_contrato, or codigo_entidad of the root entity.

    Returns:
    - **nodes**: All entities within 2 hops of the root.
    - **edges**: All relationships connecting those nodes.
    - **truncated**: true when the graph was cut at 300 nodes or 500 edges.
    - **root_id**: ID of the root node for graph centering.

    Each edge includes a **_label** field with a Spanish-language description
    of the relationship type for display (PRIV-03: no bare assertions).

    Timeout: queries exceeding 30 seconds return HTTP 408.
    """
    try:
        subgraph = await get_subgraph(id=id, session=session, privacy=privacy)
    except TimeoutError:
        raise HTTPException(
            status_code=408,
            detail="Graph query timed out. Try a more specific entity ID.",
        )

    if subgraph is None:
        raise HTTPException(status_code=404, detail=f"No entity found with id: {id}")

    freshness = await get_freshness(session)
    return APIResponse(
        data=GraphResponse(**subgraph),
        meta=ResponseMeta(**build_response_meta(freshness)),
    )
