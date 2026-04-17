"""
Contractor profile service.

Resolves a contractor ID (NIT -> Empresa, cedula -> Persona) and returns
a complete profile: contracts, sanctions, related entities.

Design:
- NIT -> Empresa profile with EJECUTA contracts + SANCIONADO sanctions + REPRESENTA persons
- Cedula -> Persona profile with REPRESENTA companies + EMPLEA entities + SANCIONADO sanctions
- Contracts paginated to 100 most recent; total count always included
- Every relationship result includes fuente for provenance (PRIV-03)
"""
import re
from neo4j import AsyncSession
from neo4j.time import DateTime as Neo4jDateTime, Date as Neo4jDate
from middleware.privacy import PrivacyFilter


def _serialize_neo4j(obj: dict) -> dict:
    """Convert neo4j.time types to ISO strings for JSON serialization."""
    out = {}
    for k, v in obj.items():
        if isinstance(v, (Neo4jDateTime, Neo4jDate)):
            out[k] = v.iso_format()
        else:
            out[k] = v
    return out

_NIT_PATTERN = re.compile(r"^[\d.\-]+$")


def _normalize_id(id_str: str) -> str:
    return re.sub(r"[.\-]", "", id_str.strip())


def _is_numeric(id_str: str) -> bool:
    return bool(_NIT_PATTERN.match(id_str.strip()))


async def get_contractor_profile(
    id: str,
    session: AsyncSession,
    privacy: PrivacyFilter,
    page: int = 1,
    page_size: int = 100,
) -> dict | None:
    """
    Return a full contractor profile for the given NIT or cedula.

    Returns None if no entity is found.
    """
    normalized = _normalize_id(id)
    skip = (page - 1) * page_size

    # Determine entity type: try Empresa first (NIT), then Persona (cedula)
    empresa = await _get_empresa_profile(normalized, session, privacy, skip, page_size)
    if empresa:
        return empresa

    persona = await _get_persona_profile(normalized, session, privacy)
    return persona


async def _get_empresa_profile(
    nit: str,
    session: AsyncSession,
    privacy: PrivacyFilter,
    skip: int,
    page_size: int,
) -> dict | None:
    """Aggregate Empresa profile: contracts, sanctions, representatives."""

    # Count total contracts first (no LIMIT)
    count_result = await session.run(
        """
        MATCH (e:Empresa {nit: $nit})-[:EJECUTA]->(c:Contrato)
        RETURN count(c) AS total
        """,
        nit=nit,
    )
    count_record = await count_result.single()
    if count_record is None:
        # Check if Empresa exists at all
        exists_result = await session.run(
            "MATCH (e:Empresa {nit: $nit}) RETURN e LIMIT 1", nit=nit
        )
        if not await exists_result.single():
            return None
        contratos_total = 0
    else:
        contratos_total = count_record["total"]

    # Fetch paginated contracts with entidad info
    contratos_result = await session.run(
        """
        MATCH (e:Empresa {nit: $nit})-[:EJECUTA]->(c:Contrato)
        OPTIONAL MATCH (entidad:EntidadPublica)-[:ADJUDICO]->(c)
        RETURN
          c.id_contrato AS id_contrato,
          c.objeto AS objeto,
          c.valor AS valor,
          c.fecha_inicio AS fecha_inicio,
          c.fecha_fin AS fecha_fin,
          c.modalidad AS modalidad,
          c.fuente AS fuente,
          entidad.nombre AS entidad_nombre,
          entidad.codigo_entidad AS entidad_codigo
        ORDER BY c.fecha_inicio DESC
        SKIP $skip LIMIT $page_size
        """,
        nit=nit,
        skip=skip,
        page_size=page_size,
    )
    contratos = await contratos_result.data()

    # Sanctions
    sanciones_result = await session.run(
        """
        MATCH (e:Empresa {nit: $nit})-[:SANCIONADO]->(s:Sancion)
        RETURN
          s.id_sancion AS id_sancion,
          s.tipo AS tipo,
          s.fecha AS fecha,
          s.autoridad AS autoridad,
          s.descripcion AS descripcion,
          s.fuente AS fuente
        ORDER BY s.fecha DESC
        LIMIT 50
        """,
        nit=nit,
    )
    sanciones = await sanciones_result.data()

    # Representatives (Persona -> Empresa)
    representantes_result = await session.run(
        """
        MATCH (p:Persona)-[r:REPRESENTA]->(e:Empresa {nit: $nit})
        RETURN
          p.cedula AS cedula,
          p.nombre AS nombre,
          r.cargo AS cargo,
          r.fecha_inicio AS desde
        LIMIT 20
        """,
        nit=nit,
    )
    representantes_raw = await representantes_result.data()

    # Apply privacy filter to representative persona properties
    representantes = [
        privacy.filter_node("Persona", rep) for rep in representantes_raw
    ]

    # Fetch the Empresa node itself
    empresa_result = await session.run(
        """
        MATCH (e:Empresa {nit: $nit})
        RETURN e
        LIMIT 1
        """,
        nit=nit,
    )
    empresa_record = await empresa_result.single()
    if not empresa_record:
        return None
    empresa_props = _serialize_neo4j(dict(empresa_record["e"]))

    return {
        "tipo": "Empresa",
        "empresa": empresa_props,
        "contratos": contratos,
        "contratos_total": contratos_total,
        "sanciones": sanciones,
        "representantes": representantes,
    }


async def _get_persona_profile(
    cedula: str,
    session: AsyncSession,
    privacy: PrivacyFilter,
) -> dict | None:
    """Aggregate Persona profile: companies, employers, sanctions."""
    persona_result = await session.run(
        """
        MATCH (p:Persona {cedula: $cedula})
        RETURN p LIMIT 1
        """,
        cedula=cedula,
    )
    persona_record = await persona_result.single()
    if not persona_record:
        return None

    persona_props = privacy.filter_node("Persona", _serialize_neo4j(dict(persona_record["p"])))

    # Companies represented
    empresas_result = await session.run(
        """
        MATCH (p:Persona {cedula: $cedula})-[r:REPRESENTA]->(e:Empresa)
        RETURN
          e.nit AS nit,
          e.razon_social AS razon_social,
          e.fuente AS fuente,
          r.cargo AS cargo,
          r.fecha_inicio AS desde
        ORDER BY r.fecha_inicio DESC
        LIMIT 50
        """,
        cedula=cedula,
    )
    empresas = await empresas_result.data()

    # Employing entities
    empleadores_result = await session.run(
        """
        MATCH (p:Persona {cedula: $cedula})-[r:EMPLEA_EN]->(entidad:EntidadPublica)
        RETURN
          entidad.codigo_entidad AS codigo_entidad,
          entidad.nombre AS nombre,
          r.cargo AS cargo,
          r.nivel AS nivel,
          r.desde AS desde
        LIMIT 20
        """,
        cedula=cedula,
    )
    empleadores = await empleadores_result.data()

    # Sanctions
    sanciones_result = await session.run(
        """
        MATCH (p:Persona {cedula: $cedula})-[:SANCIONADO]->(s:Sancion)
        RETURN
          s.id_sancion AS id_sancion,
          s.tipo AS tipo,
          s.fecha AS fecha,
          s.autoridad AS autoridad,
          s.descripcion AS descripcion,
          s.fuente AS fuente
        ORDER BY s.fecha DESC
        LIMIT 50
        """,
        cedula=cedula,
    )
    sanciones = await sanciones_result.data()

    return {
        "tipo": "Persona",
        "persona": persona_props,
        "empresas_representadas": empresas,
        "empleadores": empleadores,
        "sanciones": sanciones,
    }
