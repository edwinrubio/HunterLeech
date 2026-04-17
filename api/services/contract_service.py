"""
Contract detail service.

Returns full contract information for a given id_contrato:
- Contrato node properties (valor, objeto, modalidad, fecha, fuente)
- Adjudicating EntidadPublica (ADJUDICO relationship)
- Executing contractor: Empresa or Persona (EJECUTA relationship)
- Competing oferentes if any (PARTICIPO relationship via Proceso)

All fields include fuente for provenance (PRIV-03).
"""
from neo4j import AsyncSession
from neo4j.time import DateTime as Neo4jDateTime, Date as Neo4jDate
from middleware.privacy import PrivacyFilter


def _serialize_neo4j(obj: dict) -> dict:
    out = {}
    for k, v in obj.items():
        if isinstance(v, (Neo4jDateTime, Neo4jDate)):
            out[k] = v.iso_format()
        else:
            out[k] = v
    return out


async def get_contract_detail(
    id_contrato: str,
    session: AsyncSession,
    privacy: PrivacyFilter,
) -> dict | None:
    """
    Return full detail for a contract by id_contrato.

    Returns None if no contract found with that ID.
    """
    # Main contract + entidad + executing contractor
    result = await session.run(
        """
        MATCH (c:Contrato {id_contrato: $id_contrato})
        OPTIONAL MATCH (entidad:EntidadPublica)-[:ADJUDICO]->(c)
        OPTIONAL MATCH (ejecutor:Empresa)-[:EJECUTA]->(c)
        OPTIONAL MATCH (ejecutor_persona:Persona)-[:EJECUTA]->(c)
        RETURN
          c AS contrato,
          entidad AS entidad,
          ejecutor AS ejecutor_empresa,
          ejecutor_persona AS ejecutor_persona
        LIMIT 1
        """,
        id_contrato=id_contrato,
    )
    record = await result.single()
    if not record:
        return None

    contrato_props = dict(record["c"])
    entidad_props = dict(record["entidad"]) if record["entidad"] else None
    ejecutor_empresa = dict(record["ejecutor_empresa"]) if record["ejecutor_empresa"] else None
    ejecutor_persona_raw = dict(record["ejecutor_persona"]) if record["ejecutor_persona"] else None
    ejecutor_persona = (
        privacy.filter_node("Persona", ejecutor_persona_raw)
        if ejecutor_persona_raw else None
    )

    # Find related Proceso and competing oferentes
    proceso_result = await session.run(
        """
        MATCH (c:Contrato {id_contrato: $id_contrato})
        OPTIONAL MATCH (c)-[:GENERADO_DE]->(p:Proceso)
        OPTIONAL MATCH (oferente:Empresa)-[part:PARTICIPO]->(p)
        RETURN
          p.referencia_proceso AS referencia_proceso,
          p.tipo AS tipo_proceso,
          p.estado AS estado_proceso,
          collect(DISTINCT {
            nit: oferente.nit,
            razon_social: oferente.razon_social,
            resultado: part.resultado
          }) AS oferentes
        LIMIT 1
        """,
        id_contrato=id_contrato,
    )
    proceso_record = await proceso_result.single()
    proceso = None
    if proceso_record and proceso_record["referencia_proceso"]:
        proceso = {
            "referencia_proceso": proceso_record["referencia_proceso"],
            "tipo": proceso_record["tipo_proceso"],
            "estado": proceso_record["estado_proceso"],
            "oferentes": [o for o in proceso_record["oferentes"] if o.get("nit")],
        }

    return {
        "contrato": contrato_props,
        "entidad": entidad_props,
        "ejecutor": ejecutor_empresa or ejecutor_persona,
        "ejecutor_tipo": "Empresa" if ejecutor_empresa else ("Persona" if ejecutor_persona else None),
        "proceso": proceso,
    }
