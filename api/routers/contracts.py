"""
Contract detail router: GET /api/v1/contract/{id}

Returns full contract record with adjudicating entity, executing contractor,
and competing oferentes from the associated procurement process.
Rate limited to 60/minute — simple node lookup.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from neo4j import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from dependencies import get_neo4j_session, get_privacy_filter
from middleware.privacy import PrivacyFilter
from models.responses import APIResponse, ResponseMeta
from services.contract_service import get_contract_detail
from services.freshness_service import get_freshness, build_response_meta

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/contract/{id}", response_model=APIResponse[dict])
@limiter.limit("60/minute")
async def contract_detail(
    request: Request,
    id: str,
    session: AsyncSession = Depends(get_neo4j_session),
    privacy: PrivacyFilter = Depends(get_privacy_filter),
):
    """
    Contract detail by id_contrato.

    Returns contract metadata (valor, objeto, modalidad, fechas),
    the adjudicating public entity, the executing contractor,
    and competing oferentes from the associated procurement process.
    All fields include fuente (data source) for provenance.
    """
    detail = await get_contract_detail(id_contrato=id, session=session, privacy=privacy)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Contract not found: {id}")

    freshness = await get_freshness(session)
    return APIResponse(
        data=detail,
        meta=ResponseMeta(**build_response_meta(freshness)),
    )
