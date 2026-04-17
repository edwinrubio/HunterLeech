"""
Freshness service: query SourceIngestion nodes to report last ETL run per source.

SourceIngestion nodes are written by ETL pipelines on each successful run.
If no node exists for a source, last_ingested_at is null (not yet ingested).
Results are cached for 5 minutes to avoid a Neo4j query on every API request.
"""
import time
from datetime import datetime, timezone
from neo4j import AsyncSession

# Simple TTL cache: {dataset_id: {data, expires_at}}
_cache: dict = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


async def get_freshness(session: AsyncSession) -> list[dict]:
    """
    Return freshness records for all known data sources.

    Returns:
        List of dicts with keys: dataset_id, nombre, last_ingested_at, record_count
    """
    now = time.monotonic()
    cache_key = "freshness"

    if cache_key in _cache and _cache[cache_key]["expires_at"] > now:
        return _cache[cache_key]["data"]

    result = await session.run(
        """
        MATCH (si:SourceIngestion)
        RETURN
          si.dataset_id AS dataset_id,
          si.dataset_nombre AS nombre,
          si.last_ingested_at AS last_ingested_at,
          si.record_count AS record_count
        ORDER BY si.dataset_id
        """
    )
    records = await result.data()

    # Normalize datetime — Neo4j returns neo4j.time.DateTime objects
    freshness = []
    for r in records:
        lat = r.get("last_ingested_at")
        freshness.append({
            "dataset_id": r["dataset_id"],
            "nombre": r.get("nombre") or r["dataset_id"],
            "last_ingested_at": lat.to_native() if lat else None,
            "record_count": r.get("record_count"),
        })

    _cache[cache_key] = {"data": freshness, "expires_at": now + _CACHE_TTL_SECONDS}
    return freshness


def build_response_meta(freshness: list[dict]) -> dict:
    """Build the meta block for APIResponse."""
    return {
        "fuentes": freshness,
        "generated_at": datetime.now(timezone.utc),
    }
