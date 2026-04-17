from fastapi import APIRouter, Depends, Query
from neo4j import AsyncSession
from dependencies import get_neo4j_session

router = APIRouter(tags=["sancionados"])


@router.get("/sancionados")
async def list_sancionados(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_neo4j_session),
):
    skip = (page - 1) * page_size

    result = await session.run(
        """
        MATCH (p:Persona)-[:SANCIONADO]->(s:Sancion)
        OPTIONAL MATCH (p)-[:EJECUTA]->(c:Contrato)
        WITH p, count(DISTINCT s) AS sanciones, count(DISTINCT c) AS contratos,
             collect(DISTINCT s.tipo_sancion)[0] AS tipo_sancion
        WHERE contratos > 0
        ORDER BY sanciones DESC, contratos DESC
        SKIP $skip LIMIT $limit
        RETURN p.cedula AS cedula, p.nombre AS nombre, sanciones, contratos, tipo_sancion,
               p.fuente AS fuente
        """,
        skip=skip,
        limit=page_size,
    )
    rows = await result.data()
    return {"data": rows, "meta": {"page": page, "page_size": page_size}}
