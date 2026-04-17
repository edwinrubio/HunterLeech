"""
CLI entrypoint for HunterLeech pattern detection.

Usage:
    python -m etl.pattern_detection.run_flags
    python -m etl.pattern_detection.run_flags --pattern pat01
    python -m etl.pattern_detection.run_flags --pattern all --dry-run

This script is intended to be run:
    1. Manually after ETL ingestion for testing
    2. Automatically by APScheduler after nightly ETL (see etl/run.py)
    3. From Docker Compose as a one-shot service profile
"""

import argparse
import asyncio
import logging
import sys

from etl.pattern_detection.detector import PatternDetector, PATTERNS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HunterLeech: ejecutar deteccion de patrones de corrupcion en Neo4j"
    )
    parser.add_argument(
        "--pattern",
        choices=["all"] + list(PATTERNS.keys()),
        default="all",
        help="Patron a ejecutar. 'all' ejecuta todos. Default: all",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar que se ejecutaria sin modificar Neo4j",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()

    logger.info(
        "Iniciando deteccion de patrones — pattern=%s dry_run=%s",
        args.pattern,
        args.dry_run,
    )

    detector = await PatternDetector.create()
    try:
        if args.pattern == "all":
            results = await detector.run_all(dry_run=args.dry_run)
        else:
            result = await detector.run_pattern(args.pattern, dry_run=args.dry_run)
            results = {args.pattern: result}
    finally:
        await detector.close()

    # Report summary
    errors = [slug for slug, r in results.items() if r.get("error") == -1]
    if errors:
        logger.error("Patrones con errores: %s", errors)
        return 1

    logger.info("Deteccion completa. Resultados:")
    for slug, counters in results.items():
        logger.info("  %s: %s", slug, counters)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
