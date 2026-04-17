from fastapi import APIRouter, Depends, Query
from neo4j import AsyncSession
from dependencies import get_neo4j_session

router = APIRouter(tags=["empresas"])


@router.get("/empresas")
async def list_empresas(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    orden: str = Query("contratos"),
    session: AsyncSession = Depends(get_neo4j_session),
):
    skip = (page - 1) * page_size

    if orden == "nombre":
        order_clause = "ORDER BY e.razon_social ASC"
    else:
        order_clause = "ORDER BY contratos DESC"

    result = await session.run(
        f"""
        MATCH (e:Empresa)-[:EJECUTA]->(c:Contrato)
        WITH e, count(c) AS contratos
        {order_clause}
        SKIP $skip LIMIT $limit
        RETURN e.nit AS nit, e.razon_social AS razon_social, contratos,
               e.fuente AS fuente
        """,
        skip=skip,
        limit=page_size,
    )
    rows = await result.data()
    return {"data": rows, "meta": {"page": page, "page_size": page_size}}
