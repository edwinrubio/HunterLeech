---
phase: 02-full-etl
plan: 02
subsystem: etl
tags: [sigep, siri, secop-multas, pipeline, neo4j, socrata, sanctions, entity-linking]
dependency_graph:
  requires: [etl/base.py, etl/normalizers/common.py, etl/loaders/neo4j_loader.py, etl/state.py]
  provides:
    - etl/sources/sigep_servidores.py (SigepServidoresPipeline)
    - etl/sources/siri_sanciones.py (SiriSancionesPipeline)
    - etl/sources/secop_multas.py (SecopMultasPipeline)
  affects: [etl/run.py]
tech_stack:
  added: []
  patterns:
    - TDD red-green per pipeline
    - single-pass MERGE (SIGEP — Persona+EntidadPublica+EMPLEA_EN)
    - two-pass MERGE (SIRI — Sancion then Persona+SANCIONADO)
    - three-pass MERGE (Multas — Sancion+Entidad+IMPUSO, Empresa+MULTADO, Persona+MULTADO)
    - name-heuristic contratista classifier (no discriminator field)
    - strip-before-normalize pattern (SIRI trailing whitespace)
key_files:
  created:
    - etl/sources/sigep_servidores.py
    - etl/sources/siri_sanciones.py
    - etl/sources/secop_multas.py
    - etl/tests/test_sigep_servidores.py
    - etl/tests/test_siri_sanciones.py
    - etl/tests/test_secop_multas.py
  modified:
    - etl/run.py
decisions:
  - SIGEP EntidadPublica MERGEs on nombre (not codigo_entidad — SIGEP has no codigo_entidad; null MERGE would violate unique constraint)
  - SIGEP nombre field excluded from Persona records entirely (field contains numerodeidentificacion due to privacy redaction, not a real name)
  - SIRI cedula_raw = (row.get("numero_identificacion") or "").strip() BEFORE normalize_cedula() (trailing whitespace padding in source data)
  - SIRI fecha_efectos_juridicos stored as DD/MM/YYYY string (no ISO parse — sorting uses numero_siri ASC instead)
  - SIRI Persona.nombre set ON CREATE only, not ON MATCH (preserves names from SECOP if person already exists)
  - Multas id_sancion is composite (nit_entidad + numero_resolucion + doc) — no globally unique key in dataset
  - Multas classify_contratista_type() uses name-based heuristics (no tipodocproveedor discriminator field available)
  - Multas EntidadPublica MERGEs on nit property (not codigo_entidad — dataset provides nit_entidad only)
metrics:
  duration: 6min
  completed: 2026-04-10T02:23:21Z
  tasks: 3
  files: 7
---

# Phase 2 Plan 2: Three Remaining Socrata Pipelines Summary

**One-liner:** Three new ETL pipelines (SIGEP Servidores, SIRI Sanciones, SECOP Multas) with Persona/EntidadPublica/Sancion MERGE patterns, entity linking via shared cedula/NIT namespace, and critical pitfall handling (SIGEP nombre exclusion, SIRI whitespace stripping, Multas name-heuristic classification).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 (RED) | Failing tests for SigepServidoresPipeline | d484518 | etl/tests/test_sigep_servidores.py |
| 1 (GREEN) | Implement SigepServidoresPipeline | 82589f0 | etl/sources/sigep_servidores.py |
| 2 (RED) | Failing tests for SiriSancionesPipeline | d250602 | etl/tests/test_siri_sanciones.py |
| 2 (GREEN) | Implement SiriSancionesPipeline | 09547bc | etl/sources/siri_sanciones.py |
| 3 (RED) | Failing tests for SecopMultasPipeline | 505cf56 | etl/tests/test_secop_multas.py |
| 3 (GREEN) | Implement SecopMultasPipeline + register all in run.py | 56f14ad | etl/sources/secop_multas.py, etl/run.py |

## What Was Built

### SigepServidoresPipeline (dataset 2jzx-383z)
- Paginates SIGEP Servidores Publicos endpoint sorted by `fecha_de_vinculaci_n ASC`
- Supports incremental loads via `$where fecha_de_vinculaci_n > '{last_run_at}'`
- MERGE `EntidadPublica` on `nombre` (not `codigo_entidad` — SIGEP has no such field)
- MERGE `Persona` on `cedula` from `numerodeidentificacion` field
- `nombre` API field intentionally excluded — contains numerodeidentificacion (privacy redaction)
- `_parse_salario()` handles comma-thousands format: `"1,440,300"` -> `1440300.0`
- `EMPLEA_EN` relationship carries cargo, salario_basico, fecha_vinculacion, dependencia

### SiriSancionesPipeline (dataset iaeu-rcn6)
- Full reload (44K rows — no incremental filter; sort by `numero_siri ASC`)
- Two-pass MERGE: Sancion nodes first, then Persona + `SANCIONADO` relationship
- `cedula_raw = (row.get("numero_identificacion") or "").strip()` — strip BEFORE normalize
- `fecha_efectos_juridicos` stored as DD/MM/YYYY string — no ISO conversion
- `nombre_completo` assembled from 4 name parts, skipping `None` and `"/"` placeholders
- Persona.nombre set ON CREATE only (not ON MATCH) — preserves SECOP-sourced names

### SecopMultasPipeline (dataset 4n4q-k399)
- Paginates sorted by `fecha_de_publicacion ASC` with incremental filter support
- `classify_contratista_type()` module-level function: name-heuristic classifier for empresa vs persona (no `tipodocproveedor` in this dataset)
- Composite `id_sancion`: `f"{nit_entidad}_{numero_de_resolucion}_{doc_clean}"`
- `normalize_nit()` on `nit_entidad` strips check digit: `"890000858-1"` -> `"890000858"`
- Three-pass MERGE: EntidadPublica+Sancion+IMPUSO, Empresa+MULTADO, Persona+MULTADO
- EntidadPublica MERGEs on `nit` property (Multas provides nit_entidad, not codigo_entidad)

### etl/run.py
All 5 pipelines registered: `secop_integrado`, `secop_ii_contratos`, `sigep_servidores`, `siri_sanciones`, `secop_multas`. CLI `--help` lists all choices.

## Entity Linking (ETL-06)

Entity linking across sources is implicit via shared key namespaces:
- `Persona.cedula` — same namespace in SECOP, SIGEP, SIRI, Multas
- `Empresa.nit` — same namespace in SECOP and Multas
- Any MERGE on `cedula` for an existing Persona automatically links all sources

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| SIGEP EntidadPublica MERGE on `nombre` | No `codigo_entidad` in SIGEP; MERGE on null violates unique constraint |
| SIGEP `nombre` field excluded | Field contains `numerodeidentificacion` (privacy redaction) — would corrupt Persona.nombre |
| SIRI `.strip()` before `normalize_cedula()` | Source data has trailing whitespace padding; normalize would fail without prior strip |
| SIRI `fecha_efectos_juridicos` as string | DD/MM/YYYY can't be lexicographically sorted; sort uses `numero_siri ASC` instead |
| SIRI `ON MATCH SET` only `updated_at` | Preserves superior SECOP-sourced name data; SIRI names are secondary |
| Multas composite `id_sancion` | No single globally unique identifier in dataset; composite prevents false merges |
| `classify_contratista_type()` name heuristics | No `tipodocproveedor` field in Multas; legal suffix detection covers most cases |
| Multas `MERGE (ent:EntidadPublica {nit: ...})` | Dataset provides `nit_entidad`, not `codigo_entidad`; uses `nit` property to avoid constraint collision |

## Test Results

```
101 passed, 1 warning in 0.29s
```

- `test_sigep_servidores.py`: 25 tests
- `test_siri_sanciones.py`: 23 tests
- `test_secop_multas.py`: 28 tests
- `test_secop_ii_contratos.py`: 25 tests (from Plan 01, unaffected)

## Deviations from Plan

None — plan executed exactly as written. All three pipelines implemented with the field mappings, Cypher patterns, and skip conditions specified. All pitfalls handled per the `<interfaces>` section in the plan.

## Known Stubs

None. All fields are wired from live API data; no hardcoded placeholders in any pipeline.

## Self-Check: PASSED
