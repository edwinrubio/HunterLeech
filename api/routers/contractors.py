"""
Contractor profile router: GET /api/v1/contractor/{id}

Accepts NIT (Empresa) or cedula (Persona). Resolves automatically.
Rate limited to 30/minute — heavier aggregation query than search.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from neo4j import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from dependencies import get_neo4j_session, get_privacy_filter
from middleware.privacy import PrivacyFilter
from models.responses import APIResponse, ResponseMeta
from services.contractor_service import get_contractor_profile
from services.freshness_service import get_freshness, build_response_meta

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/contractor/{id}", response_model=APIResponse[dict])
@limiter.limit("30/minute")
async def contractor_profile(
    request: Request,
    id: str,
    page: int = 1,
    page_size: int = 100,
    session: AsyncSession = Depends(get_neo4j_session),
    privacy: PrivacyFilter = Depends(get_privacy_filter),
):
    """
    Full contractor profile by NIT or cedula.

    - **id**: NIT (empresa) or cedula (persona). Dots and hyphens are stripped.
    - **page**: Contract page number (default 1)
    - **page_size**: Contracts per page (default 100, max 100)

    Returns all contracts (paginated), active and historical sanctions,
    and related entities. Includes provenance source for every record.
    """
    page_size = min(page_size, 100)
    profile = await get_contractor_profile(
        id=id, session=session, privacy=privacy, page=page, page_size=page_size
    )
    if profile is None:
        raise HTTPException(status_code=404, detail=f"No entity found with id: {id}")

    freshness = await get_freshness(session)
    return APIResponse(
        data=profile,
        meta=ResponseMeta(**build_response_meta(freshness)),
    )
