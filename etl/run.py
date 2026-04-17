"""
ETL pipeline runner.

Usage:
    python -m etl.run secop_integrado [--full]

    --full   Ignore last_run_at state, load all records from the beginning.

The runner:
1. Loads run state from .etl_state/{dataset_id}.json
2. Opens Neo4jLoader (verifies constraints — aborts if missing)
3. Runs the pipeline, saving state after each batch
4. Updates last_run_at to now on successful completion
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime, timezone

from etl.config import etl_config
from etl.loaders.neo4j_loader import Neo4jLoader
from etl.sources.secop_integrado import SecopIntegradoPipeline
from etl.sources.secop_ii_contratos import SecopIIContratosPipeline
from etl.sources.sigep_servidores import SigepServidoresPipeline
from etl.sources.siri_sanciones import SiriSancionesPipeline
from etl.sources.secop_multas import SecopMultasPipeline
from etl.sources.secop_ii_procesos import SecopIIProcesosPipeline
from etl.state import load_state, save_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

PIPELINES = {
    "secop_integrado":    SecopIntegradoPipeline,
    "secop_ii_contratos": SecopIIContratosPipeline,
    "sigep_servidores":   SigepServidoresPipeline,
    "siri_sanciones":     SiriSancionesPipeline,
    "secop_multas":       SecopMultasPipeline,
    "secop_ii_procesos":  SecopIIProcesosPipeline,
}


async def run_pipeline(pipeline_name: str, full: bool = False) -> None:
    if pipeline_name not in PIPELINES:
        logger.error("Unknown pipeline: %s. Available: %s", pipeline_name, list(PIPELINES))
        sys.exit(1)

    PipelineClass = PIPELINES[pipeline_name]
    pipeline = PipelineClass()
    state = load_state(pipeline.name)

    if full:
        state["last_run_at"] = None
        state["last_page"] = 0
        state["records_loaded"] = 0
        logger.info("Full load mode — ignoring previous run state")
    else:
        logger.info(
            "Incremental load — last_run_at=%s, last_page=%d, records_loaded=%d",
            state.get("last_run_at"),
            state.get("last_page", 0),
            state.get("records_loaded", 0),
        )

    state["status"] = "running"
    save_state(pipeline.name, state)

    async with Neo4jLoader(
        uri=etl_config.neo4j_uri,
        user=etl_config.neo4j_user,
        password=etl_config.neo4j_password,
        batch_size=etl_config.batch_size,
    ) as loader:
        try:
            async for page_df in pipeline.extract(state):
                records = pipeline.transform(page_df)
                if records:
                    await pipeline.load(records, loader)
                state["records_loaded"] = state.get("records_loaded", 0) + len(records)
                save_state(pipeline.name, state)

            state["last_run_at"] = datetime.now(timezone.utc).isoformat()
            state["status"] = "completed"
            save_state(pipeline.name, state)
            logger.info(
                "Pipeline %s completed. Total records: %d",
                pipeline_name,
                state["records_loaded"],
            )
        except Exception:
            state["status"] = "interrupted"
            save_state(pipeline.name, state)
            logger.exception("Pipeline %s interrupted", pipeline_name)
            raise


def main():
    parser = argparse.ArgumentParser(description="HunterLeech ETL runner")
    parser.add_argument("pipeline", choices=list(PIPELINES), help="Pipeline to run")
    parser.add_argument("--full", action="store_true", help="Full reload (ignore previous state)")
    args = parser.parse_args()
    asyncio.run(run_pipeline(args.pipeline, full=args.full))


if __name__ == "__main__":
    main()
