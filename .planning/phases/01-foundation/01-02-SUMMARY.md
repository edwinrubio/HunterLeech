---
phase: 01-foundation
plan: 02
subsystem: etl/normalizers + docs/privacy
tags: [normalization, privacy, entity-resolution, nit, cedula, tdd]
dependency_graph:
  requires: []
  provides: [PRIV-01, INFRA-03]
  affects: [etl/sources/secop_integrado.py (Plan 03), entity MERGE keys]
tech_stack:
  added: [pytest]
  patterns: [TDD red-green, null sentinel policy, composite MERGE key]
key_files:
  created:
    - etl/__init__.py
    - etl/normalizers/__init__.py
    - etl/normalizers/common.py
    - etl/normalizers/test_common.py
    - docs/privacy/field_classification.md
  modified: []
decisions:
  - "Hyphen in NIT separates check digit — strip everything after last hyphen before normalizing"
  - "normalize_nit returns None (not empty string) for unresolvable identifiers — null sentinel policy"
  - "Contrato MERGE key: numero_del_contrato + '_' + origen (scopes SECOPI vs SECOPII)"
  - "normalize_cedula delegates to normalize_nit — same logic, cedulas have no check digit"
  - "No PRIVADA or SENSIBLE fields in SECOP Integrado rpmr-utcd dataset"
metrics:
  duration: "3 min"
  completed_date: "2026-04-10"
  tasks_completed: 2
  files_created: 5
---

# Phase 01 Plan 02: NIT Normalization + Privacy Classification Summary

**One-liner:** NIT/cedula normalization with null-sentinel policy (4 functions, 23 tests green) + Ley 1581/2012 field classification for all 22 SECOP Integrado fields (PRIV-01 gate satisfied).

## What Was Built

### Task 1: NIT/cedula normalization module (TDD)

**Exported functions from `etl/normalizers/common.py`:**

| Function | Purpose | Returns |
|----------|---------|---------|
| `normalize_nit(raw)` | Strip check digit, dots, spaces, leading zeros | `str` (digits only) or `None` |
| `normalize_cedula(raw)` | Same as normalize_nit (no check digit) | `str` (digits only) or `None` |
| `normalize_razon_social(raw)` | Lowercase, accent-strip, suffix-remove dedup key | `str` or `None` |
| `classify_proveedor_type(doc, tipo)` | empresa / persona / desconocido | `Literal["empresa","persona","desconocido"]` |

**Test results:** 23 tests, 23 passed, 0 failed (100% pass rate)

**Test coverage by function:**
- `normalize_nit`: 9 test cases
- `normalize_cedula`: 3 test cases
- `normalize_razon_social`: 5 test cases
- `classify_proveedor_type`: 6 test cases

### Task 2: Privacy field classification (PRIV-01 gate)

**SEMIPRIVADA field handling rules:**

| Field | Rule |
|-------|------|
| `nom_raz_social_contratista` | Store always. PUBLIC_MODE=true: show in contract context only, not search autocomplete for natural persons |
| `documento_proveedor` | When tipo=NIT (legal entity): PUBLICA. When tipo=cedula/NIT-Persona-Natural: SEMIPRIVADA, no free-text search in PUBLIC_MODE |

**All 22 SECOP Integrado fields classified.** 20 PUBLICA, 2 SEMIPRIVADA. No PRIVADA or SENSIBLE fields.

## Key Decisions Made

1. **Check digit stripping via hyphen split:** NIT format "890399010-4" separates the check digit with a hyphen. The normalizer uses `rsplit('-', 1)[0]` to drop everything after the last hyphen before any other cleaning. This is safer than blindly dropping the last digit.

2. **Null sentinel policy enforced in code:** `normalize_nit()` returns `None` — never `""`, `"N/A"`, or `"0"`. The module docstring explicitly states: "Do NOT store empty string or N/A as NIT in Neo4j — these create false uniqueness collisions via MERGE."

3. **Contrato composite MERGE key:** `numero_del_contrato + "_" + origen` — necessary because SECOPI and SECOPII reused contract numbers during the 2015-2018 transition period. Phase 2 will add cross-origin deduplication.

4. **classify_proveedor_type uses substring matching:** `"nit de persona natural" in normalized_tipo` catches all variants (spacing, capitalization) after lowercasing. Order of checks matters: persona keywords checked before plain "nit" to avoid "Nit de Persona Natural" being classified as "empresa".

## Normalization Edge Cases Discovered

| Input | Expected | Behavior | Notes |
|-------|----------|----------|-------|
| `"890399010-4"` | `"890399010"` | Hyphen splits at check digit | Fixed during GREEN phase — initial regex stripped hyphen but kept all digits |
| `"0"` | `None` | Leading zero strip yields empty string | Single zero is ambiguous identifier — correct to reject |
| `"ABC123"` | `None` | Mixed alphanumeric fails isdigit() | Correct — non-numeric NITs are invalid |
| `"CONSTRUCCIONES S.A.S."` | `"construcciones"` | Suffix list ordered longest-first | "s.a.s." must precede "s.a." to avoid partial match |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed check digit not being stripped from NIT**
- **Found during:** Task 1 GREEN phase (first test run)
- **Issue:** The regex `re.sub(r'[\s.\-]', '', raw.strip())` stripped the hyphen character but left the check digit as part of the number. `"890399010-4"` became `"8903990104"` instead of `"890399010"`.
- **Fix:** Changed approach to split on the last hyphen first (`rsplit('-', 1)[0]`) before stripping remaining dots/spaces. This correctly isolates and discards the check digit.
- **Files modified:** `etl/normalizers/common.py`
- **Commit:** 6fb7bed

## Commits

| Hash | Message |
|------|---------|
| 284d4e7 | test(01-02): add failing tests for NIT/cedula normalization module (RED) |
| 6fb7bed | feat(01-02): implement NIT/cedula normalization module (GREEN) |
| a33dae4 | feat(01-02): add SECOP Integrado field privacy classification document (PRIV-01) |

## Gates Satisfied

- **PRIV-01:** All 22 SECOP Integrado fields classified with Ley 1581/2012 rationale
- **INFRA-03:** NIT/cedula normalization functions exist, tested, and enforce null sentinel policy
- ETL pipeline (Plan 03) may now import `from etl.normalizers.common import normalize_nit`

## Self-Check: PASSED
