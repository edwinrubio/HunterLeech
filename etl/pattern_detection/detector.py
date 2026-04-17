"""
HunterLeech Pattern Detection Engine.

Runs batch Cypher queries to detect red flag patterns in the procurement graph.
Results are stored as properties on existing nodes — no new nodes or relationships created.

Design:
- Each pattern is a separate .cypher file in queries/
- PatternDetector loads and executes each query file against Neo4j
- Queries are idempotent (SET + CLEAR pattern) — safe to run repeatedly
- flag_computed_at datetime is set on every flagged node for freshness tracking
- Run after ETL ingestion (ETL fills data, detector reads and annotates it)

Usage:
    detector = await PatternDetector.create()
    results = await detector.run_all()
    await detector.close()
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from neo4j import AsyncGraphDatabase, AsyncDriver

logger = logging.getLogger(__name__)

# Mapping pattern slug to .cypher filename
PATTERNS: dict[str, str] = {
    "pat01": "pat01_single_bidder.cypher",
    "pat02": "pat02_short_tender.cypher",
    "pat03": "pat03_contract_amendment.cypher",
    "pat04": "pat04_direct_award_concentration.cypher",
    "pat05": "pat05_sanctioned_contractor.cypher",
}

QUERIES_DIR = Path(__file__).parent / "queries"


class PatternDetectionError(Exception):
    """Raised when a pattern detection query fails."""


class PatternDetector:
    """
    Executes all red flag pattern detection Cypher queries against Neo4j.

    Instantiate via PatternDetector.create() for async setup.
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    @classmethod
    async def create(
        cls,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> "PatternDetector":
        """
        Create a PatternDetector with a Neo4j driver.
        If uri/user/password not provided, reads from etl.config.etl_config.
        """
        if uri is None:
            from etl.config import etl_config

            uri = etl_config.neo4j_uri
            user = etl_config.neo4j_user
            password = etl_config.neo4j_password

        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        await driver.verify_connectivity()
        logger.info("PatternDetector connected to Neo4j at %s", uri)
        return cls(driver)

    async def close(self) -> None:
        await self._driver.close()

    def _load_query(self, filename: str) -> str:
        """Load a Cypher query file from the queries/ directory."""
        path = QUERIES_DIR / filename
        if not path.exists():
            raise PatternDetectionError(f"Query file not found: {path}")
        return path.read_text(encoding="utf-8")

    async def run_pattern(
        self,
        slug: str,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """
        Run a single pattern detection query by slug (e.g. "pat01").

        Returns a dict of result counters from the query (flagged_true, cleared, etc.).
        In dry_run mode, the query is parsed but not executed.
        """
        if slug not in PATTERNS:
            raise PatternDetectionError(
                f"Unknown pattern: {slug}. Valid: {list(PATTERNS.keys())}"
            )

        filename = PATTERNS[slug]
        query_text = self._load_query(filename)

        # Split multi-statement .cypher files on semicolons
        # Each statement is a separate MATCH...RETURN block
        # Strip comment-only lines from within each statement before execution
        raw_parts = query_text.split(";\n")
        statements = []
        for part in raw_parts:
            lines = [
                line for line in part.strip().splitlines()
                if line.strip() and not line.strip().startswith("//")
            ]
            cypher = "\n".join(lines).strip()
            if cypher:
                statements.append(cypher)

        if dry_run:
            logger.info("[DRY RUN] %s: would execute %d statements", slug, len(statements))
            return {"dry_run": len(statements)}

        counters: dict[str, int] = {}
        async with self._driver.session(database="neo4j") as session:
            for i, stmt in enumerate(statements):
                if not stmt.strip():
                    continue
                try:
                    result = await session.run(stmt)
                    record = await result.single()
                    summary = await result.consume()
                    if record:
                        for key in record.keys():
                            counters[f"{slug}_{i}_{key}"] = record[key] or 0
                    props_set = summary.counters.properties_set
                    logger.debug("%s stmt[%d]: %d properties set", slug, i, props_set)
                except Exception as exc:
                    logger.error("Error in %s stmt[%d]: %s", slug, i, exc)
                    raise PatternDetectionError(
                        f"Query failed for {slug} statement {i}: {exc}"
                    ) from exc

        logger.info("%s complete. Counters: %s", slug, counters)
        return counters

    async def run_all(self, dry_run: bool = False) -> dict[str, dict[str, int]]:
        """
        Run all pattern detection queries in sequence.

        Returns a dict mapping pattern slug to its result counters.
        """
        all_results: dict[str, dict[str, int]] = {}
        for slug in PATTERNS:
            logger.info("Running pattern: %s", slug)
            try:
                result = await self.run_pattern(slug, dry_run=dry_run)
                all_results[slug] = result
            except PatternDetectionError as exc:
                logger.error("Pattern %s failed: %s", slug, exc)
                all_results[slug] = {"error": -1}
        return all_results
