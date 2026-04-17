---
phase: 02-full-etl
plan: 03
subsystem: etl
tags: [neo4j, schema, verification, entity-linking, cross-source]
dependency_graph:
  requires:
    - etl/sources/sigep_servidores.py
    - etl/sources/siri_sanciones.py
    - etl/sources/secop_multas.py
    - etl/sources/secop_ii_contratos.py
    - infra/neo4j/schema.cypher
  provides:
    - infra/neo4j/schema.cypher (entidad_nombre index)
    - scripts/verify-etl-phase2.sh
  affects: []
tech_stack:
  added: []
  patterns:
    - docker exec cypher-shell verification pattern
    - IF NOT EXISTS idempotent index creation
key_files:
  created:
    - scripts/verify-etl-phase2.sh
  modified:
    - infra/neo4j/schema.cypher
decisions:
  - entidad_nombre index added as optional performance index (not a uniqueness constraint — SIGEP MERGE is on nombre, not a constrained field)
  - verify-etl-phase2.sh uses docker exec pattern matching apply-schema.sh for consistency
  - Task 2 (live pipeline run + human verification) deferred — requires docker compose up with live Neo4j
metrics:
  duration: 3min
  completed: 2026-04-10T02:28:00Z
  tasks: 1 of 2 (Task 2 deferred — human verification)
  files: 2
---

# Phase 2 Plan 3: Schema Index + ETL Verification Summary

**One-liner:** SIGEP performance index (entidad_nombre) added to schema.cypher and automated graph integrity verification script written with cross-source entity linking and super node checks.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add entidad_nombre index + write verify script | 1a298cc | infra/neo4j/schema.cypher, scripts/verify-etl-phase2.sh |

## Tasks Deferred

| # | Task | Reason |
|---|------|--------|
| 2 | Run pipelines + human verify cross-source entity linking | Requires live Docker environment (`docker compose up`). Cannot run in current YOLO/non-interactive execution context. |

## What Was Built

### infra/neo4j/schema.cypher (updated)

Added performance index after `contrato_modalidad`:

```cypher
// Added for Phase 2: SIGEP entities merge on nombre, not codigo_entidad
CREATE INDEX entidad_nombre IF NOT EXISTS
  FOR (e:EntidadPublica) ON (e.nombre);
```

This index accelerates SIGEP `SigepServidoresPipeline` MERGE operations, which resolve `EntidadPublica` by `nombre` (not `codigo_entidad` — SIGEP has no such field). Without this index, each MERGE performs a full label scan. At 265K SIGEP rows this matters for load time.

### scripts/verify-etl-phase2.sh

Automated verification script that runs against live Neo4j via `docker exec cypher-shell`. Checks:

1. **Node counts by label** — confirms all pipelines populated the graph
2. **Relationship counts by type** — confirms EMPLEA_EN, SANCIONADO, EJECUTA, MULTADO, IMPUSO, ADJUDICO all exist
3. **Provenance coverage** — confirms `fuente` property is set on all node types (ETL-05)
4. **Cross-source entity linking** — two queries:
   - `MATCH (p:Persona)-[:EMPLEA_EN]->() WHERE (p)-[:SANCIONADO]->()` — SIGEP+SIRI links
   - `MATCH (p:Persona)-[:EJECUTA]->() WHERE (p)-[:SANCIONADO]->()` — SECOP+SIRI links
5. **Super node check** — detects any node with >10,000 relationships (would indicate a categorical-as-node Anti-Pattern 1 violation)
6. **Sancion node samples** — spot-checks SIRI and Multas sanction links

Usage:
```bash
docker compose up -d
bash scripts/apply-schema.sh
python -m etl.run siri_sanciones --full
python -m etl.run sigep_servidores --full
python -m etl.run secop_multas --full
python -m etl.run secop_ii_contratos --full
bash scripts/verify-etl-phase2.sh
```

## Human Verification (Task 2) — Deferred

Task 2 is a `checkpoint:human-verify` gate requiring a live running Neo4j instance. The plan calls for:

1. `docker compose up -d`
2. `bash scripts/apply-schema.sh` — apply updated schema with entidad_nombre index
3. Run all four Phase 2 pipelines
4. `bash scripts/verify-etl-phase2.sh`
5. Confirm: non-zero counts, at least 1 cross-source linked Persona (EMPLEA_EN + SANCIONADO), zero super nodes

**To complete verification:** Run the commands above in the project root. The verification script will print results. Confirm the cross-source linking query returns > 0, and the super node query returns 0 rows.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `entidad_nombre` as INDEX not CONSTRAINT | SIGEP entity names are not globally unique; multiple entries may share a name. An index accelerates MERGE lookups without enforcing uniqueness. |
| verify script uses `docker exec -i` | Matches apply-schema.sh pattern; `-i` flag required for stdin piping of inline Cypher strings |
| `NEO4J_CONTAINER` env var with fallback | `hunterleech-neo4j-1` is the default Docker Compose container name; override via env for non-default setups |

## Deviations from Plan

### Auto-fixed Issues

None.

### Scope Notes

Task 2 (live run + human-verify) is structurally deferred, not a deviation. The plan marks it `type="checkpoint:human-verify" gate="blocking"` — it is a human action checkpoint by design. Execution in YOLO mode without a live Docker environment cannot complete this gate automatically.

## Known Stubs

None. `verify-etl-phase2.sh` contains no placeholder text or hardcoded mock data — all Cypher queries are real and will execute against live Neo4j.

## Self-Check: PASSED
