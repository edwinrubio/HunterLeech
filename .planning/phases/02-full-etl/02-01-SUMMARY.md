---
phase: 02-full-etl
plan: 01
subsystem: etl
tags: [secop-ii, pipeline, neo4j, socrata, contracts]
dependency_graph:
  requires: [etl/base.py, etl/normalizers/common.py, etl/loaders/neo4j_loader.py, etl/state.py]
  provides: [etl/sources/secop_ii_contratos.py, SecopIIContratosPipeline]
  affects: [etl/run.py, etl/normalizers/common.py]
tech_stack:
  added: []
  patterns: [three-pass MERGE, TDD red-green, Socrata pagination]
key_files:
  created:
    - etl/sources/secop_ii_contratos.py
    - etl/tests/__init__.py
    - etl/tests/test_secop_ii_contratos.py
  modified:
    - etl/run.py
    - etl/normalizers/common.py
decisions:
  - id_contrato used directly as Contrato MERGE key (no composite; globally unique in SECOP II)
  - _parse_valor_secop2() does NOT strip dots (SECOP II uses plain integer strings, not thousands-separated)
  - classify_proveedor_type() fixed to strip accents before keyword comparison (handles "Cedula de Ciudadania" with and without accents)
  - load() always calls merge_batch() exactly 3 times regardless of empresa/persona record count
metrics:
  duration: 4min
  completed: 2026-04-10T02:14:48Z
  tasks: 2
  files: 5
---

# Phase 2 Plan 1: SECOP II Contratos ETL Pipeline Summary

**One-liner:** SecopIIContratosPipeline extending BasePipeline with three-pass MERGE (EntidadPublica+Contrato, Empresa, Persona), direct id_contrato key, and plain-float valor parsing for SECOP II's integer-string format.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 (RED) | Failing tests for SecopIIContratosPipeline | 2fd3fa1 | etl/tests/__init__.py, etl/tests/test_secop_ii_contratos.py |
| 1 (GREEN) | Implement SecopIIContratosPipeline | d640c06 | etl/sources/secop_ii_contratos.py, etl/normalizers/common.py |
| 2 | Register secop_ii_contratos in run.py | e736309 | etl/run.py |

## What Was Built

A new ETL pipeline `SecopIIContratosPipeline` (dataset `jbjy-vk9h`) that:

- Paginates the SECOP II Contratos Electronicos Socrata endpoint sorted by `fecha_de_firma ASC`
- Supports incremental loads via `$where fecha_de_firma > '{last_run_at}'`
- Transforms rows into Neo4j-ready dicts with full provenance (`fuente`, `ingested_at`, `url_fuente`)
- Executes three separate MERGE passes (Anti-Pattern 1 compliance):
  1. All records: MERGE `EntidadPublica` + `Contrato` + `ADJUDICO` relationship
  2. Empresa records only: MERGE `Empresa` + `EJECUTA` relationship (filtered by `proveedor_type=="empresa"` and non-None `nit_contratista`)
  3. Persona records only: MERGE `Persona` + `EJECUTA` relationship (filtered by `proveedor_type=="persona"` and non-None `cedula_contratista`)
- Cross-source entity linking is implicit: `Empresa.nit` and `Persona.cedula` share the same normalized namespace as SECOP Integrado

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `id_contrato` used directly as MERGE key | SECOP II IDs (format `CO1.PCCNTR.<n>`) are globally unique; no composite needed unlike SECOP I |
| `_parse_valor_secop2()` — no dot removal | SECOP II stores valor as plain integer strings; SECOP I uses dots as thousands separators. Separate helper prevents applying the wrong parsing to SECOP II data |
| `load()` always calls `merge_batch()` 3 times | Consistent with SecopIntegradoPipeline pattern; empty list batches are safe no-ops in Neo4jLoader |
| `modalidad_de_contratacion` — no accent in SECOP II field name | Contrast with SECOP I's `modalidad_de_contrataci_n` (accented); mapped correctly per RESEARCH.md |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed accent handling in classify_proveedor_type()**
- **Found during:** Task 1 GREEN phase — test `test_cedula_tipodoc_classified_as_persona` failed
- **Issue:** `classify_proveedor_type()` in `etl/normalizers/common.py` lowercased the `tipo_documento` string but did not strip Unicode combining characters (accents). SECOP II sends `tipodocproveedor="Cédula de Ciudadanía"` with accents; the keyword list uses unaccented `"cedula de ciudadania"`. The string never matched, so all SECOP II cedula records were classified as `"desconocido"`.
- **Fix:** Added `unicodedata.normalize("NFD", ...)` + combining character stripping in `classify_proveedor_type()` before keyword comparison. This makes the function handle both accented (SECOP II) and unaccented (SECOP I) inputs correctly.
- **Files modified:** `etl/normalizers/common.py`
- **Commit:** d640c06

**2. [Rule 3 - Blocking] Installed pytest-asyncio for async test support**
- **Found during:** Task 1 GREEN phase — 5 async tests failed with "async def functions are not natively supported"
- **Issue:** `pytest-asyncio` was not installed; async test methods using `@pytest.mark.asyncio` could not be collected.
- **Fix:** Installed `pytest-asyncio` (v1.3.0) via pip.
- **Files modified:** None (system package install)

## Verification Results

```
25 passed, 1 warning in 0.26s
```

```
python3 -c "from etl.sources.secop_ii_contratos import SecopIIContratosPipeline; print(SecopIIContratosPipeline.name)"
# Output: jbjy-vk9h

python3 -m etl.run --help
# Output includes: {secop_integrado,secop_ii_contratos}
```

## Known Stubs

None. All fields are wired from live API data; no hardcoded placeholders in the pipeline.

## Self-Check: PASSED
