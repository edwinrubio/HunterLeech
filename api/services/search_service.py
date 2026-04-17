"""
Search service: entity lookup by NIT, cedula, or name.

Routing:
  - Numeric query (digits only after stripping .-) -> exact NIT or cedula match
  - Non-numeric query -> fulltext index fuzzy search on entity_search_idx

Both paths return a list of result dicts with keys:
  tipo, id, nombre, score, fuente
"""
import re
from neo4j import AsyncSession
from middleware.privacy import PrivacyFilter

_NIT_PATTERN = re.compile(r"^[\d.\-]+$")

# Known source dataset names for provenance labels
DATASET_NAMES = {
    "rpmr-utcd": "SECOP Integrado",
    "jbjy-vk9h": "SECOP II Contratos",
    "p6dx-8zbt": "SECOP II Procesos",
    "4n4q-k399": "Multas y Sanciones SECOP",
    "iaeu-rcn6": "SIRI Procuraduria",
    "2jzx-383z": "SIGEP Servidores Publicos",
}


def _is_id_query(q: str) -> bool:
    """Return True if q looks like a NIT or cedula (digits and separators only)."""
    return bool(_NIT_PATTERN.match(q.strip()))


def _normalize_id(q: str) -> str:
    """Strip dots and hyphens from a NIT/cedula string."""
    return re.sub(r"[.\-]", "", q.strip())


async def search(
    q: str,
    session: AsyncSession,
    privacy: PrivacyFilter,
    tipo: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    Search entities by name (fulltext) or by NIT/cedula (exact).

    Args:
        q: Search query — name fragment or NIT/cedula
        session: Neo4j async session
        privacy: PrivacyFilter instance for field redaction
        tipo: Optional filter — 'empresa', 'persona', or 'entidad'
        limit: Max results (default 20, max 50)

    Returns:
        List of entity result dicts, ordered by relevance score.
    """
    limit = min(limit, 50)

    if _is_id_query(q):
        return await _exact_id_search(q, session, privacy, limit)
    else:
        return await _fulltext_search(q, session, privacy, tipo, limit)


async def _exact_id_search(
    q: str, session: AsyncSession, privacy: PrivacyFilter, limit: int
) -> list[dict]:
    """Exact match on NIT or cedula."""
    normalized = _normalize_id(q)
    result = await session.run(
        """
        MATCH (n)
        WHERE n.nit = $q OR n.cedula = $q
        RETURN
          labels(n)[0] AS tipo,
          coalesce(n.nit, n.cedula, n.codigo_entidad) AS id,
          coalesce(n.razon_social, n.nombre) AS nombre,
          n.fuente AS fuente,
          1.0 AS score
        LIMIT $limit
        """,
        q=normalized,
        limit=limit,
    )
    records = await result.data()
    return [_format_result(r, privacy) for r in records]


async def _fulltext_search(
    q: str,
    session: AsyncSession,
    privacy: PrivacyFilter,
    tipo: str | None,
    limit: int,
) -> list[dict]:
    """Fuzzy fulltext search using entity_search_idx Lucene index."""
    # Append ~ for fuzzy matching (Damerau-Levenshtein distance 1)
    fuzzy_q = f"{q}~" if len(q) >= 4 else q

    # Build optional label filter
    label_filter = ""
    if tipo == "empresa":
        label_filter = "AND 'Empresa' IN labels(node)"
    elif tipo == "persona":
        label_filter = "AND 'Persona' IN labels(node)"
    elif tipo == "entidad":
        label_filter = "AND 'EntidadPublica' IN labels(node)"

    result = await session.run(
        f"""
        CALL db.index.fulltext.queryNodes('entity_search_idx', $q)
        YIELD node, score
        WHERE score > 0.1 {label_filter}
        RETURN
          labels(node)[0] AS tipo,
          coalesce(node.nit, node.cedula, node.codigo_entidad) AS id,
          coalesce(node.razon_social, node.nombre) AS nombre,
          node.fuente AS fuente,
          score
        ORDER BY score DESC
        LIMIT $limit
        """,
        q=fuzzy_q,
        limit=limit,
    )
    records = await result.data()
    return [_format_result(r, privacy) for r in records]


def _format_result(r: dict, privacy: PrivacyFilter) -> dict:
    """Format a raw Cypher result row into a search result dict."""
    label = r.get("tipo", "Unknown")
    return {
        "tipo": label,
        "id": r.get("id"),
        "nombre": r.get("nombre"),
        "fuente": r.get("fuente"),
        "score": round(float(r.get("score", 1.0)), 4),
        # Source dataset label for provenance (PRIV-03)
        "fuente_nombre": DATASET_NAMES.get(r.get("fuente", ""), r.get("fuente", "")),
    }
