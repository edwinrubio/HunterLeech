"""
Neo4jLoader: async MERGE batch writer for HunterLeech ETL pipelines.

CRITICAL RULES (from ARCHITECTURE.md Anti-Pattern 1):
- NEVER merge full patterns in one MERGE: (a)-[:R]->(b)
- Always MERGE each node separately, then MERGE relationship
- Batch size 500-1000 rows via UNWIND for efficiency

CONSTRAINT VERIFICATION:
- verify_constraints() is called at loader startup
- ETL aborts with RuntimeError if any required constraint is absent
- This makes it impossible to load data without the schema in place
"""

import logging
from neo4j import AsyncGraphDatabase, AsyncSession

logger = logging.getLogger(__name__)

# All constraint names that must exist before any ETL runs.
# Defined in infra/neo4j/schema.cypher and created via scripts/apply-schema.sh
REQUIRED_CONSTRAINTS = {
    "empresa_nit",
    "persona_cedula",
    "contrato_id",
    "proceso_ref",
    "sancion_id",
    "entidad_codigo",
}


async def verify_constraints(session: AsyncSession) -> None:
    """
    Verify all required Neo4j uniqueness constraints exist.
    Raises RuntimeError if any are missing.
    Must be called before any MERGE statement.
    """
    result = await session.run("SHOW CONSTRAINTS YIELD name RETURN name")
    existing = {record["name"] async for record in result}
    missing = REQUIRED_CONSTRAINTS - existing
    if missing:
        raise RuntimeError(
            f"ETL aborted: missing Neo4j constraints: {sorted(missing)}. "
            "Run scripts/apply-schema.sh first, then retry."
        )
    logger.info("Constraint verification passed: all %d constraints present", len(REQUIRED_CONSTRAINTS))


class Neo4jLoader:
    """
    Manages Neo4j connection and batched MERGE writes.

    Usage:
        async with Neo4jLoader(uri, user, password) as loader:
            await verify_constraints(session)
            await loader.merge_batch(records, cypher)
    """

    def __init__(self, uri: str, user: str, password: str, batch_size: int = 500):
        self._uri = uri
        self._user = user
        self._password = password
        self.batch_size = batch_size
        self._driver = None

    async def __aenter__(self):
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
            max_connection_lifetime=3600,
            max_connection_pool_size=10,
        )
        await self._driver.verify_connectivity()
        # Verify constraints on every startup — not just first run
        async with self._driver.session(database="neo4j") as session:
            await verify_constraints(session)
        return self

    async def __aexit__(self, *args):
        if self._driver:
            await self._driver.close()

    async def merge_batch(self, records: list[dict], cypher: str) -> int:
        """
        Execute UNWIND MERGE for a list of record dicts.
        Sends records in batches of self.batch_size.
        Returns total records written.
        """
        total = 0
        async with self._driver.session(database="neo4j") as session:
            for i in range(0, len(records), self.batch_size):
                batch = records[i : i + self.batch_size]
                await session.run(cypher, batch=batch)
                total += len(batch)
                logger.debug("Merged batch of %d records (%d total)", len(batch), total)
        return total
