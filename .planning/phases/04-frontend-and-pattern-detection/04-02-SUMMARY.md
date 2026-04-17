---
phase: 04-frontend-and-pattern-detection
plan: "02"
subsystem: etl/pattern_detection
tags: [pattern-detection, cypher, neo4j, batch, idempotent, red-flags]
dependency_graph:
  requires:
    - etl/config.py (etl_config for Neo4j credentials)
    - etl/loaders/neo4j_loader.py (AsyncGraphDatabase pattern)
    - infra/neo4j/schema.cypher (existing node labels)
  provides:
    - etl/pattern_detection/detector.py (PatternDetector class)
    - etl/pattern_detection/run_flags.py (CLI entrypoint)
    - etl/pattern_detection/queries/*.cypher (5 idempotent flag queries)
  affects:
    - :Proceso nodes (flag_oferente_unico, flag_periodo_corto)
    - :Contrato nodes (flag_adicion_valor)
    - :Empresa nodes (flag_concentracion_directa, flag_contratista_sancionado)
    - :Persona nodes (flag_contratista_sancionado)
tech_stack:
  added: []
  patterns:
    - Idempotent Cypher via SET TRUE + CLEAR (SET FALSE) dual-statement pattern
    - AsyncGraphDatabase.driver with verify_connectivity() on startup
    - Cypher file loading via Path(__file__).parent / 'queries' / filename
    - Per-pattern error isolation in run_all() (continues on PatternDetectionError)
key_files:
  created:
    - etl/pattern_detection/__init__.py
    - etl/pattern_detection/detector.py
    - etl/pattern_detection/run_flags.py
    - etl/pattern_detection/queries/pat01_single_bidder.cypher
    - etl/pattern_detection/queries/pat02_short_tender.cypher
    - etl/pattern_detection/queries/pat03_contract_amendment.cypher
    - etl/pattern_detection/queries/pat04_direct_award_concentration.cypher
    - etl/pattern_detection/queries/pat05_sanctioned_contractor.cypher
  modified: []
decisions:
  - "etl_config (not settings) is the correct import from etl.config — plan template had wrong name"
  - "Cypher statements split on ';\\n' to handle multi-statement .cypher files"
  - "PatternDetector uses database='neo4j' session parameter for explicit default DB targeting"
metrics:
  duration: "3min"
  completed_date: "2026-04-10"
  tasks_completed: 2
  files_created: 8
---

# Phase 4 Plan 02: Pattern Detection Engine Summary

Five idempotent Cypher batch detectors writing red-flag boolean properties directly to Neo4j nodes (PAT-01 through PAT-05), executed by a Python PatternDetector class with CLI runner.

## What Was Built

### Cypher Query Files

All 5 pattern queries are in `etl/pattern_detection/queries/`. Each file follows the SET TRUE + CLEAR (SET FALSE) dual-statement pattern for full idempotency.

| Pattern | File | Statements | Node Type | Flag Property |
|---------|------|------------|-----------|---------------|
| PAT-01 | pat01_single_bidder.cypher | 2 | :Proceso | flag_oferente_unico |
| PAT-02 | pat02_short_tender.cypher | 2 | :Proceso | flag_periodo_corto, flag_periodo_dias |
| PAT-03 | pat03_contract_amendment.cypher | 2 | :Contrato | flag_adicion_valor, flag_adicion_pct |
| PAT-04 | pat04_direct_award_concentration.cypher | 2 | :Empresa | flag_concentracion_directa, flag_concentracion_entidades |
| PAT-05 | pat05_sanctioned_contractor.cypher | 4 | :Empresa + :Persona | flag_contratista_sancionado |

All flagged nodes also receive `flag_computed_at = datetime()` for freshness tracking.

### Python Module

**`etl/pattern_detection/detector.py`** — `PatternDetector` class:
- `PatternDetector.create(uri, user, password)` — async factory, falls back to `etl_config` when creds not passed
- `run_pattern(slug, dry_run=False)` — loads .cypher file, splits on `;\n`, executes each statement
- `run_all(dry_run=False)` — runs all 5 patterns; isolates errors per-pattern (never aborts full run)
- `close()` — async driver shutdown

**`etl/pattern_detection/run_flags.py`** — CLI entrypoint:
- `python -m etl.pattern_detection.run_flags` — runs all 5 patterns
- `--pattern [all|pat01|pat02|pat03|pat04|pat05]` — selective execution
- `--dry-run` — skips Neo4j writes, logs statement counts only
- Returns exit code 0 (success) or 1 (any pattern errored)

## Verification Results

```
# Module import check
python3 -c "from etl.pattern_detection.detector import PatternDetector, PATTERNS; print('OK', list(PATTERNS.keys()))"
OK ['pat01', 'pat02', 'pat03', 'pat04', 'pat05']

# Syntax check (both files)
SYNTAX OK: etl/pattern_detection/detector.py
SYNTAX OK: etl/pattern_detection/run_flags.py

# All 5 Cypher flag property checks: PASS
```

Live Neo4j test was not run (stack not running during execution). The `--dry-run` flag allows testing without a live database.

## PAT-04 Performance Notes

PAT-04 (`pat04_direct_award_concentration.cypher`) performs the most graph traversal:
1. First pass: joins Empresa-EJECUTA->Contrato<-ADJUDICO-EntidadPublica (rolling 12-month window) to compute per-empresa value
2. Second pass per entity: sums all direct-award contracts for that entity in the same window
3. Filters pairs where empresa_valor / entidad_total > 0.50
4. Aggregates flagging entities per empresa

This query is O(N * E) in the worst case where N = direct-award empresas and E = entities. If runtime exceeds 30s on production data, mitigation options are:
- Add a `fecha_firma` composite index on `:Contrato(modalidad, fecha_firma)`
- Restrict CLEAR pass to only empresas that recently had contracts expire from the rolling window
- Consider splitting into two separate Cypher statements (compute + update) for explicit transaction control

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed import name: etl_config not settings**
- **Found during:** Task 2 implementation
- **Issue:** Plan template used `from etl.config import settings` but `etl/config.py` exports `etl_config` (instance of `ETLConfig`). Every other ETL file uses `etl_config`. Using `settings` would raise `ImportError` at runtime.
- **Fix:** Used `from etl.config import etl_config` and `etl_config.neo4j_uri`, `.neo4j_user`, `.neo4j_password`
- **Files modified:** `etl/pattern_detection/detector.py`
- **Commit:** 5125ef9

## Known Stubs

None — all 5 Cypher queries are fully implemented with real property names from the schema. The Python runner connects to live Neo4j. No placeholder data.

## Self-Check: PASSED

- `etl/pattern_detection/__init__.py` exists: FOUND
- `etl/pattern_detection/detector.py` exists: FOUND
- `etl/pattern_detection/run_flags.py` exists: FOUND
- All 5 .cypher files exist in `etl/pattern_detection/queries/`: FOUND
- Commit c7d8dcd (Task 1): FOUND
- Commit 5125ef9 (Task 2): FOUND
- `python3 -c "from etl.pattern_detection.detector import PatternDetector, PATTERNS"`: PASS
