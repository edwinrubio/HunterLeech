"""
Search router: GET /api/v1/search

Handles entity search by NIT, cedula, or name with fuzzy matching.
Rate limited to 60 requests/minute per IP.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from neo4j import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from dependencies import get_neo4j_session, get_privacy_filter
from middleware.privacy import PrivacyFilter
from models.responses import APIResponse, ResponseMeta, FuenteMeta
from services.search_service import search as do_search
from services.freshness_service import get_freshness, build_response_meta

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/search", response_model=APIResponse[list[dict]])
@limiter.limit("60/minute")
async def search(
    request: Request,
    q: str,
    tipo: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_neo4j_session),
    privacy: PrivacyFilter = Depends(get_privacy_filter),
):
    """
    Search entities by NIT, cedula, or name.

    - **q**: Search query. Numeric strings trigger exact NIT/cedula lookup.
      Text strings trigger fulltext fuzzy search.
    - **tipo**: Optional filter. Values: `empresa`, `persona`, `entidad`
    - **limit**: Max results (1-50, default 20)
    """
    results = await do_search(q=q, session=session, privacy=privacy, tipo=tipo, limit=limit)
    freshness = await get_freshness(session)
    return APIResponse(
        data=results,
        meta=ResponseMeta(**build_response_meta(freshness)),
    )
