from fastapi import APIRouter, Depends, Query
from neo4j import AsyncSession
from dependencies import get_neo4j_session

router = APIRouter(tags=["alertas"])


@router.get("/alertas/resumen")
async def alertas_resumen(
    session: AsyncSession = Depends(get_neo4j_session),
):
    """Summary counts for each pattern detection flag."""
    result = await session.run(
        """
        OPTIONAL MATCH (e1:Empresa {flag_contratista_recurrente: true})
        WITH count(e1) AS contratista_recurrente
        OPTIONAL MATCH (c2:Contrato {flag_contrato_express: true})
        WITH contratista_recurrente, count(c2) AS contrato_express
        OPTIONAL MATCH (p3:Persona {flag_red_amplia: true})
        WITH contratista_recurrente, contrato_express, count(p3) AS red_amplia
        OPTIONAL MATCH (e4:Empresa {flag_concentracion_directa: true})
        WITH contratista_recurrente, contrato_express, red_amplia, count(e4) AS concentracion_directa
        OPTIONAL MATCH (n5 {flag_contratista_sancionado: true})
        WHERE n5:Empresa OR n5:Persona
        RETURN contratista_recurrente, contrato_express, red_amplia,
               concentracion_directa, count(n5) AS contratista_sancionado
        """
    )
    row = await result.single()
    if not row:
        empty = {"contratista_recurrente": 0, "contrato_express": 0, "red_amplia": 0,
                 "concentracion_directa": 0, "contratista_sancionado": 0}
        return {"data": empty, "meta": {}}
    return {
        "data": {
            "contratista_recurrente": row["contratista_recurrente"],
            "contrato_express": row["contrato_express"],
            "red_amplia": row["red_amplia"],
            "concentracion_directa": row["concentracion_directa"],
            "contratista_sancionado": row["contratista_sancionado"],
        },
        "meta": {},
    }


@router.get("/alertas/{patron}")
async def alertas_detalle(
    patron: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_neo4j_session),
):
    """Paginated list of entities flagged by a specific pattern."""
    skip = (page - 1) * page_size

    queries = {
        "contratista_recurrente": """
            MATCH (e:Empresa {flag_contratista_recurrente: true})-[:EJECUTA]->(c:Contrato)<-[:ADJUDICO]-(ent:EntidadPublica)
            WITH e, ent, count(c) AS contratos_con_entidad
            ORDER BY contratos_con_entidad DESC
            WITH e, collect({entidad: ent.nombre, contratos: contratos_con_entidad})[0] AS top
            RETURN e.nit AS id,
                   'Empresa' AS tipo,
                   e.razon_social AS nombre,
                   e.flag_recurrente_max AS max_contratos,
                   top.entidad AS entidad_principal,
                   e.flag_computed_at AS detectado
            ORDER BY e.flag_recurrente_max DESC
            SKIP $skip LIMIT $limit
        """,
        "contrato_express": """
            MATCH (c:Contrato {flag_contrato_express: true})<-[:EJECUTA]-(e)
            WHERE e:Empresa OR e:Persona
            OPTIONAL MATCH (c)<-[:ADJUDICO]-(ent:EntidadPublica)
            RETURN c.id_contrato AS id,
                   'Contrato' AS tipo,
                   c.objeto AS nombre,
                   ent.nombre AS entidad,
                   COALESCE(e.razon_social, e.nombre) AS contratista,
                   COALESCE(e.nit, e.cedula) AS contratista_id,
                   c.flag_express_dias AS dias,
                   toFloat(c.valor) AS valor,
                   c.flag_computed_at AS detectado
            ORDER BY c.flag_express_dias ASC
            SKIP $skip LIMIT $limit
        """,
        "red_amplia": """
            MATCH (p:Persona {flag_red_amplia: true})
            RETURN p.cedula AS id,
                   'Persona' AS tipo,
                   p.nombre AS nombre,
                   p.flag_red_amplia_entidades AS num_entidades,
                   p.flag_computed_at AS detectado
            ORDER BY p.flag_red_amplia_entidades DESC
            SKIP $skip LIMIT $limit
        """,
        "concentracion_directa": """
            MATCH (e:Empresa {flag_concentracion_directa: true})
            OPTIONAL MATCH (e)-[:EJECUTA]->(c:Contrato)
            WITH e, count(c) AS contratos
            RETURN e.nit AS id,
                   'Empresa' AS tipo,
                   e.razon_social AS nombre,
                   contratos,
                   e.flag_concentracion_entidades AS entidades_concentradas,
                   e.flag_computed_at AS detectado
            ORDER BY contratos DESC
            SKIP $skip LIMIT $limit
        """,
        "contratista_sancionado": """
            MATCH (n)-[:SANCIONADO]->(s:Sancion)
            WHERE (n:Empresa OR n:Persona) AND n.flag_contratista_sancionado = true
            OPTIONAL MATCH (n)-[:EJECUTA]->(c:Contrato)
            WITH n,
                 labels(n)[0] AS tipo,
                 count(DISTINCT s) AS sanciones,
                 count(DISTINCT c) AS contratos
            RETURN COALESCE(n.nit, n.cedula) AS id,
                   tipo,
                   COALESCE(n.razon_social, n.nombre) AS nombre,
                   sanciones,
                   contratos,
                   n.flag_computed_at AS detectado
            ORDER BY sanciones DESC, contratos DESC
            SKIP $skip LIMIT $limit
        """,
    }

    if patron not in queries:
        return {"data": [], "meta": {"page": page, "error": "patron no reconocido"}}

    result = await session.run(queries[patron], skip=skip, limit=page_size)
    rows = await result.data()

    # Serialize neo4j temporal types
    for row in rows:
        for k, v in row.items():
            if hasattr(v, "iso_format"):
                row[k] = v.iso_format()

    return {"data": rows, "meta": {"page": page, "page_size": page_size, "patron": patron}}
