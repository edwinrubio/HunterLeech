"""
BasePipeline: abstract base class for all HunterLeech ETL pipelines.

Each source dataset gets one concrete pipeline class that implements:
- extract(): async generator yielding Polars DataFrames
- transform(df): returns list[dict] ready for Neo4j MERGE
- load(records, loader): calls loader.merge_batch() with transformed records

The run() method orchestrates the pipeline with state tracking.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator
import polars as pl

from etl.loaders.neo4j_loader import Neo4jLoader
from etl.state import RunState, save_state


class BasePipeline(ABC):
    name: str  # dataset ID e.g. "rpmr-utcd"
    label: str  # human label e.g. "SECOP Integrado"

    @abstractmethod
    async def extract(self, state: RunState) -> AsyncGenerator[pl.DataFrame, None]:
        """Paginate source API, yield DataFrames of PAGE_SIZE rows."""
        ...

    @abstractmethod
    def transform(self, df: pl.DataFrame) -> list[dict]:
        """
        Convert a DataFrame page into a list of record dicts.
        Applies normalization (must use etl.normalizers.common — no inline logic).
        Returns only records that are safe to MERGE (non-None keys).
        """
        ...

    @abstractmethod
    def get_cypher(self) -> str:
        """Return the UNWIND ... MERGE Cypher for this pipeline's node types."""
        ...

    async def load(self, records: list[dict], loader: Neo4jLoader) -> int:
        """
        Default load: single MERGE pass using get_cypher().
        Override in subclasses that need multiple MERGE passes (e.g. SecopIntegradoPipeline).
        Returns total records written.
        """
        return await loader.merge_batch(records, self.get_cypher())

    async def run(self, loader: Neo4jLoader, state: RunState) -> RunState:
        """
        Execute full extract -> transform -> load cycle.
        Updates state after each batch and saves to disk.
        """
        total_loaded = 0
        async for page_df in self.extract(state):
            records = self.transform(page_df)
            if records:
                await self.load(records, loader)
                total_loaded += len(records)
            state["records_loaded"] = state.get("records_loaded", 0) + len(records)
            save_state(self.name, state)
        return state
