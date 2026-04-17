"""
ETL Bootloader — runs on container start when LOAD_DATA_BOOTLOADER=true.

1. Waits for Neo4j to be healthy
2. Applies schema constraints (idempotent)
3. Runs all 6 ETL pipelines in sequence
4. Runs pattern detector
5. Exits with code 0 on success

Skips entirely if LOAD_DATA_BOOTLOADER is not 'true'.
"""

import asyncio
import logging
import os
import sys
import time

from neo4j import AsyncGraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("bootloader")

PIPELINE_ORDER = [
    "secop_integrado",
    "secop_ii_contratos",
    "sigep_servidores",
    "siri_sanciones",
    "secop_multas",
    "secop_ii_procesos",
]

SCHEMA_FILE = "/app/schema/schema.cypher"


async def wait_for_neo4j(uri: str, user: str, password: str, timeout: int = 300):
    """Wait until Neo4j accepts connections."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
            await driver.verify_connectivity()
            await driver.close()
            logger.info("Neo4j is ready at %s", uri)
            return
        except Exception:
            logger.info("Waiting for Neo4j... (%.0fs)", time.time() - start)
            await asyncio.sleep(5)
    logger.error("Neo4j not available after %ds", timeout)
    sys.exit(1)


async def apply_schema(uri: str, user: str, password: str):
    """Apply schema.cypher constraints and indexes."""
    if not os.path.exists(SCHEMA_FILE):
        logger.warning("Schema file not found at %s, skipping", SCHEMA_FILE)
        return

    schema_text = open(SCHEMA_FILE).read()
    statements = [
        s.strip() for s in schema_text.split(";")
        if s.strip() and not s.strip().startswith("//")
    ]

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    async with driver.session(database="neo4j") as session:
        for stmt in statements:
            # Strip comment lines within statement
            lines = [l for l in stmt.splitlines() if l.strip() and not l.strip().startswith("//")]
            cypher = "\n".join(lines).strip()
            if cypher:
                try:
                    await session.run(cypher)
                    logger.info("Applied: %s", cypher[:80])
                except Exception as e:
                    logger.warning("Schema statement skipped: %s", e)
    await driver.close()
    logger.info("Schema applied successfully")


async def run_all_pipelines():
    """Run each ETL pipeline in order."""
    from etl.run import run_pipeline

    for name in PIPELINE_ORDER:
        logger.info("=" * 60)
        logger.info("Starting pipeline: %s", name)
        logger.info("=" * 60)
        try:
            await run_pipeline(name, full=False)
            logger.info("Pipeline %s completed", name)
        except Exception:
            logger.exception("Pipeline %s failed — continuing with next", name)


async def run_pattern_detector():
    """Run all pattern detection queries."""
    from etl.pattern_detection.detector import PatternDetector

    logger.info("=" * 60)
    logger.info("Running pattern detector")
    logger.info("=" * 60)

    detector = await PatternDetector.create()
    try:
        results = await detector.run_all()
        for slug, counters in results.items():
            logger.info("  %s: %s", slug, counters)
    finally:
        await detector.close()

    logger.info("Pattern detection complete")


async def main():
    load_flag = os.environ.get("LOAD_DATA_BOOTLOADER", "false").lower()
    if load_flag != "true":
        logger.info("LOAD_DATA_BOOTLOADER is not 'true' (got '%s') — skipping ETL bootloader", load_flag)
        return

    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "changeme")

    logger.info("=" * 60)
    logger.info("HunterLeech ETL Bootloader starting")
    logger.info("=" * 60)

    # Step 1: Wait for Neo4j
    await wait_for_neo4j(uri, user, password)

    # Step 2: Apply schema
    await apply_schema(uri, user, password)

    # Step 3: Run all ETL pipelines
    await run_all_pipelines()

    # Step 4: Run pattern detector
    await run_pattern_detector()

    logger.info("=" * 60)
    logger.info("Bootloader complete — all pipelines and patterns done")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
