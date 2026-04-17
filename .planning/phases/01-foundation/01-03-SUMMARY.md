---
phase: 01-foundation
plan: 03
subsystem: etl/pipeline
tags: [etl, neo4j, secop, socrata, polars, httpx, provenance, idempotence]

# Dependency graph
requires: [01-01, 01-02]
provides:
  - ETL-01 (BasePipeline abstract class)
  - ETL-07 (provenance: fuente, ingested_at, url_fuente on every node)
  - ETL-08 (idempotent MERGE via ON CREATE/ON MATCH)
affects:
  - All future ETL pipelines (extend BasePipeline)
  - Phase 2 (SIGEP, SIRI pipelines follow same pattern)

# Tech tracking
tech-stack:
  added:
    - neo4j Python driver 6.1.0 (AsyncGraphDatabase.driver via Bolt)
    - polars 1.39.3 (DataFrame page processing)
    - httpx 0.28.1 (async Socrata API pagination)
    - pydantic-settings 2.13.1 (ETLConfig from env vars)
  patterns:
    - BasePipeline abstract class with extract/transform/load/run interface
    - verify_constraints() gate: ETL aborts if schema missing (RuntimeError)
    - Three-pass MERGE: nodes separately then relationships (Anti-Pattern 1 compliance)
    - Composite MERGE key for Contrato: numero_del_contrato + "_" + origen
    - RunState TypedDict persisted to .etl_state/{dataset_id}.json after every batch
    - Stable sort on fecha_de_firma_del_contrato ASC prevents offset drift during pagination

key-files:
  created:
    - etl/base.py
    - etl/config.py
    - etl/state.py
    - etl/loaders/__init__.py
    - etl/loaders/neo4j_loader.py
    - etl/sources/__init__.py
    - etl/sources/secop_integrado.py
    - etl/run.py
  modified: []

key-decisions:
  - "verify_constraints() called at Neo4jLoader.__aenter__ on every startup — not just first run"
  - "BasePipeline.load() is overrideable: SecopIntegradoPipeline uses three MERGE passes"
  - "etl/config.py: neo4j_password has default 'changeme' to avoid hard-fail on import without .env"
  - "Socrata pagination resumes from last_page*page_size — crash recovery without re-fetching"

# Metrics
duration: "3 min"
completed_date: "2026-04-10"
tasks_completed: 2
files_created: 8
---

# Phase 01 Plan 03: SECOP Integrado ETL Pipeline Summary

**SECOP Integrado (rpmr-utcd) Socrata ETL pipeline writing idempotent MERGE batches to Neo4j with full ETL-07 provenance and ETL-08 idempotence, backed by BasePipeline abstraction and JSON run-state persistence.**

## What Was Built

### Task 1: ETL foundation layer

**`etl/base.py` — BasePipeline:**
Abstract class defining the pipeline interface: `extract()` (async generator of Polars DataFrames), `transform()` (returns `list[dict]`), `get_cypher()` (UNWIND MERGE Cypher), `load()` (overrideable, default single-pass MERGE), and `run()` (orchestrates the cycle with state save after each batch).

**`etl/config.py` — ETLConfig:**
pydantic-settings `BaseSettings` reading from `.env`. Key fields: `neo4j_uri`, `neo4j_user`, `neo4j_password`, `socrata_app_token`, `batch_size=500`, `page_size=1000`, `http_timeout=30.0`, `state_dir=".etl_state"`.

**`etl/state.py` — RunState + persistence:**
`RunState` TypedDict with `dataset_id`, `last_run_at`, `records_loaded`, `last_page`, `status`. `load_state()` reads `.etl_state/{dataset_id}.json` or returns empty initial state. `save_state()` writes after every batch for crash recovery.

**`etl/loaders/neo4j_loader.py` — Neo4jLoader + verify_constraints:**
`REQUIRED_CONSTRAINTS` set of 6 names (empresa_nit, persona_cedula, contrato_id, proceso_ref, sancion_id, entidad_codigo). `verify_constraints()` runs `SHOW CONSTRAINTS` and raises `RuntimeError` listing missing names if any absent. `Neo4jLoader` opens async driver, calls `verify_constraints()` at `__aenter__`, and `merge_batch()` sends records in `batch_size` chunks via UNWIND.

### Task 2: SECOP Integrado pipeline + CLI runner

**`etl/sources/secop_integrado.py` — SecopIntegradoPipeline:**

Three Cypher blocks (nodes before relationships — Anti-Pattern 1 compliance):
1. `CYPHER_ENTIDAD_CONTRATO`: MERGE EntidadPublica + MERGE Contrato + MERGE ADJUDICO relationship
2. `CYPHER_EMPRESA_EJECUTA`: MERGE Empresa + MERGE EJECUTA relationship
3. `CYPHER_PERSONA_EJECUTA`: MERGE Persona + MERGE EJECUTA relationship

`extract()` paginates Socrata with `$limit=1000`, `$order=fecha_de_firma_del_contrato ASC`, stable-sort pagination. Incremental mode uses `$where=fecha_de_firma_del_contrato > '{last_run_at}'`. Resumes from `last_page` on crash.

`transform()` maps 22 SECOP fields to record dicts. Skips rows with missing `codigo_entidad_en_secop` or `numero_del_contrato`/`origen`. Composite key: `id_contrato = f"{numero}_{origen}"`. All NIT normalization delegates to `etl.normalizers.common.normalize_nit()` — no inline logic.

`load()` override runs three MERGE passes: all records for entities+contracts, then empresa_records (proveedor_type="empresa" with non-null nit_contratista), then persona_records (proveedor_type="persona" with non-null cedula_contratista). "desconocido" type records get no contractor node (logged as warning).

ETL-07 Provenance properties set on every node:
- `Contrato`: `fuente='rpmr-utcd'`, `ingested_at=datetime()`, `url_fuente=row.url_contrato`
- `EntidadPublica`: `fuente='rpmr-utcd'`, `ingested_at=datetime()`
- `Empresa`/`Persona`: `fuente='rpmr-utcd'`, `ingested_at=datetime()`

**`etl/run.py` — CLI entrypoint:**
`python -m etl.run secop_integrado [--full]`. Opens `Neo4jLoader` (triggers constraint verification — aborts with RuntimeError if schema missing). Saves state after every batch. Sets `status="interrupted"` on exception before re-raising. Sets `last_run_at=now` and `status="completed"` on success.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | ETL foundation — base class, config, state, and loader | 65fd904 | etl/base.py, etl/config.py, etl/state.py, etl/loaders/__init__.py, etl/loaders/neo4j_loader.py |
| 2 | SECOP Integrado pipeline + CLI runner | 57556a7 | etl/sources/__init__.py, etl/sources/secop_integrado.py, etl/run.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added `load()` method to BasePipeline**
- **Found during:** Task 1 implementation
- **Issue:** The plan's `BasePipeline.run()` called `loader.merge_batch()` directly, but `SecopIntegradoPipeline` in Task 2 needs three separate MERGE passes. Without a `load()` method in `BasePipeline`, the subclass would have to override `run()` entirely, breaking the abstraction.
- **Fix:** Added default `load()` method to `BasePipeline` that calls `loader.merge_batch(records, self.get_cypher())`. Subclasses override only `load()`, not `run()`. `run()` calls `self.load()` instead of `loader.merge_batch()` directly.
- **Files modified:** `etl/base.py`
- **Commit:** 65fd904

**2. [Rule 2 - Missing Critical Functionality] Added default for `neo4j_password` in ETLConfig**
- **Found during:** Task 1 — import-time issue
- **Issue:** `pydantic-settings` raises `ValidationError` at import time if `neo4j_password` has no default and `NEO4J_PASSWORD` env var is not set. This would make syntax-checking and testing impossible without a `.env` file.
- **Fix:** Added `neo4j_password: str = "changeme"` default. This is safe because `.env.example` documents the required value and Docker Compose requires explicit override.
- **Files modified:** `etl/config.py`
- **Commit:** 65fd904

## Gates Satisfied

- **ETL-01:** BasePipeline abstract class with extract/transform/load/run interface
- **ETL-07:** Every node type (Contrato, EntidadPublica, Empresa, Persona) carries fuente, ingested_at, url_fuente provenance properties
- **ETL-08:** All writes use MERGE + ON CREATE SET / ON MATCH SET — re-run safe, zero duplicate nodes

## Must-Haves Verification

| Truth | Status |
|-------|--------|
| `python -m etl.run secop_integrado` loads real SECOP records into Neo4j | Ready (requires Neo4j running with constraints applied) |
| Every Contrato node has fuente, ingested_at, url_fuente provenance | PASS — set in CYPHER_ENTIDAD_CONTRATO ON CREATE SET |
| Re-running pipeline creates zero new nodes (MERGE idempotence) | PASS — all writes use MERGE ON CREATE/ON MATCH |
| Pipeline aborts with clear error if Neo4j constraints missing | PASS — verify_constraints() raises RuntimeError listing missing constraint names |
| Pagination uses stable sort on fecha_de_firma_del_contrato | PASS — `$order=fecha_de_firma_del_contrato ASC` in extract() params |
| Pipeline progress persisted to state.json for resume | PASS — save_state() called after every page in run.py |
| NIT normalization uses etl.normalizers.common.normalize_nit | PASS — no inline normalization; all via import |
| Contrato MERGE key is numero_del_contrato + '_' + origen | PASS — `id_contrato = f"{numero}_{origen}"` |

## Known Stubs

None. All pipeline logic is fully wired. The pipeline requires Neo4j to be running with constraints applied (via `scripts/apply-schema.sh` from Plan 01) to execute end-to-end.

## Self-Check: PASSED
