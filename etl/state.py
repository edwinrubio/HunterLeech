"""
Persist pipeline run state to JSON files in .etl_state/.
Enables resume after crash without re-fetching already-loaded pages.

State file path: .etl_state/{dataset_id}.json
State schema:
{
    "dataset_id": "rpmr-utcd",
    "last_run_at": "2026-04-09T03:00:00Z",  # ISO8601 UTC — used in $where filter
    "records_loaded": 125000,
    "last_page": 125,
    "status": "completed" | "interrupted"
}
"""

import json
import os
from typing import TypedDict

from etl.config import etl_config


class RunState(TypedDict, total=False):
    dataset_id: str
    last_run_at: str | None    # ISO8601 UTC string or None for full load
    records_loaded: int
    last_page: int
    status: str                # "completed" | "interrupted" | "running"


def _state_path(dataset_id: str) -> str:
    os.makedirs(etl_config.state_dir, exist_ok=True)
    return os.path.join(etl_config.state_dir, f"{dataset_id}.json")


def load_state(dataset_id: str) -> RunState:
    """Load existing run state or return empty initial state."""
    path = _state_path(dataset_id)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return RunState(
        dataset_id=dataset_id,
        last_run_at=None,
        records_loaded=0,
        last_page=0,
        status="new",
    )


def save_state(dataset_id: str, state: RunState) -> None:
    """Persist run state to disk. Called after every batch."""
    path = _state_path(dataset_id)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
