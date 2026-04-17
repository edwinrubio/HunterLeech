---
phase: 03-backend-api
plan: "01"
subsystem: api
tags: [search, privacy, rate-limiting, neo4j-fulltext, response-envelope]
dependency_graph:
  requires: []
  provides:
    - entity_search_idx fulltext index in Neo4j schema
    - GET /api/v1/search endpoint with fuzzy name and exact NIT/cedula lookup
    - PrivacyFilter class for Ley 1581/2012 field redaction
    - APIResponse[T] envelope with meta.fuentes freshness block
    - freshness_service querying SourceIngestion nodes (5-min TTL cache)
  affects:
    - api/main.py (slowapi wired, search router registered)
    - api/dependencies.py (get_privacy_filter added)
    - infra/neo4j/schema.cypher (fulltext + source ingestion indexes added)
tech_stack:
  added:
    - slowapi==0.1.9 (rate limiting)
  patterns:
    - PrivacyFilter applied in service layer (not HTTP middleware) to retain label context
    - APIResponse[T] Generic Pydantic envelope for all endpoints
    - lru_cache(maxsize=1) for PrivacyFilter singleton
    - TTL dict cache (5 min) for freshness data to avoid per-request Neo4j queries
key_files:
  created:
    - api/middleware/__init__.py
    - api/middleware/privacy.py
    - api/models/__init__.py
    - api/models/entities.py
    - api/models/responses.py
    - api/services/__init__.py
    - api/services/freshness_service.py
    - api/services/search_service.py
    - api/routers/search.py
  modified:
    - infra/neo4j/schema.cypher
    - api/requirements.txt
    - api/main.py
    - api/dependencies.py
decisions:
  - "PrivacyFilter implemented as service-layer class (not ASGI middleware) so node label is available for per-field filtering"
  - "lru_cache(maxsize=1) used for PrivacyFilter singleton — PUBLIC_MODE is read once at startup, no runtime changes expected"
  - "Freshness cached in-process dict (5 min TTL) rather than Redis — avoids infrastructure dependency for a non-critical staleness window"
  - "Fuzzy suffix (~) appended only for queries >= 4 chars to avoid excessive Lucene fuzzy expansion on short strings"
metrics:
  duration: "~3 minutes"
  completed_date: "2026-04-10"
  tasks_completed: 4
  files_changed: 13
---

# Phase 3 Plan 01: Search Endpoint, Privacy Filter, and Response Envelope Summary

**One-liner:** Neo4j fulltext index + GET /api/v1/search with fuzzy name matching, exact NIT/cedula lookup, Ley 1581/2012 privacy filtering, 60 req/min rate limiting, and APIResponse[T] freshness envelope.

## What Was Built

### Task 1: schema.cypher — Fulltext Index

Appended to `infra/neo4j/schema.cypher`:

```cypher
CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS
FOR (n:Empresa|Persona|EntidadPublica)
ON EACH [n.razon_social, n.nombre];

CREATE INDEX source_ingestion_dataset IF NOT EXISTS
  FOR (si:SourceIngestion) ON (si.dataset_id);
```

The `entity_search_idx` Lucene fulltext index covers all three entity node types across both name properties. The `source_ingestion_dataset` index supports efficient freshness queries by ETL pipeline dataset ID.

### Task 2: slowapi + main.py update

- `slowapi==0.1.9` added to `api/requirements.txt`
- `api/main.py` updated to version `0.3.0` with:
  - `Limiter(key_func=get_remote_address)` instantiated at module level
  - `app.state.limiter = limiter` wired for slowapi middleware integration
  - `RateLimitExceeded` exception handler registered (returns HTTP 429)
  - `search_router` imported and registered at `/api/v1`

### Task 3: Privacy middleware and response envelope

**`api/middleware/privacy.py` — PrivacyFilter class:**

Protected fields stripped per node label when `PUBLIC_MODE=true`:

| Label | Protected fields |
|-------|-----------------|
| Persona | email, telefono_personal, direccion_residencia, fecha_nacimiento, numero_documento |
| Empresa | (none — legal entities are public record) |
| EntidadPublica | (none — public institutions are public) |
| Contrato | (none — SECOP contract data is public) |
| Sancion | (none — SIRI/Procuraduria sanctions are public) |
| Proceso | (none — procurement processes are public) |

Methods: `filter_node(label, props)` and `filter_graph_nodes(nodes)`.

**`api/models/responses.py` — Response envelope:**
- `FuenteMeta`: dataset_id, nombre, last_ingested_at, record_count
- `ResponseMeta`: fuentes (list[FuenteMeta]), generated_at
- `APIResponse[T]`: Generic[T] envelope with data + meta

**`api/models/entities.py` — Entity DTOs:**
EmpresaDTO, PersonaDTO (with optional protected fields), EntidadPublicaDTO, ContratoDTO, SancionDTO.

**`api/dependencies.py`** extended with `get_privacy_filter()` — `lru_cache(maxsize=1)` singleton returning `PrivacyFilter(public_mode=settings.public_mode)`.

### Task 4: Freshness service and search endpoint

**`api/services/freshness_service.py`:**
- Queries `SourceIngestion` nodes (written by ETL pipelines on each successful run)
- 5-minute TTL in-process cache using `time.monotonic()` to avoid Neo4j roundtrip per request
- `build_response_meta()` helper produces the `meta` dict for APIResponse

**`api/services/search_service.py`:**
- Numeric-only queries (digits + `.` `-`) → exact MATCH on `n.nit` or `n.cedula`
- Text queries → `db.index.fulltext.queryNodes('entity_search_idx', $q)` with `~` fuzzy suffix (>= 4 chars)
- Optional `tipo` filter injects label predicate into fulltext WHERE clause
- `limit` capped at 50; default 20
- `_format_result()` adds `fuente_nombre` human label from DATASET_NAMES map

**`api/routers/search.py` — GET /api/v1/search:**
- `@limiter.limit("60/minute")` per IP rate limiting
- `q` (required), `tipo` (optional), `limit` (optional, default 20) query params
- Returns `APIResponse[list[dict]]` with data + meta.fuentes freshness block

## Verification Results

All automated checks passed:

```
schema.cypher: CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS    PASS
requirements.txt: slowapi==0.1.9                                         PASS
middleware/privacy.py: PROTECTED_FIELDS defined                          PASS
routers/search.py: @limiter.limit("60/minute")                          PASS
models/responses.py: APIResponse[T] Generic envelope                     PASS
```

Live stack verification (requires `docker compose up -d` + `./scripts/apply-schema.sh`) not run in this execution — no running Neo4j instance available. All static checks confirmed correct.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The `meta.fuentes` array will be empty (not stubbed) when no SourceIngestion nodes exist in the graph — this is correct behavior (ETL pipelines not yet run). The array will populate automatically once Phase 2 ETL pipelines write SourceIngestion nodes.

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | 6c8863f | feat(03-01): extend schema.cypher with fulltext search index |
| 2 | 0ab1aa4 | feat(03-01): wire slowapi rate limiter and register search router |
| 3 | 4b5915d | feat(03-01): add privacy middleware and response envelope models |
| 4 | d038116 | feat(03-01): add freshness service and GET /api/v1/search endpoint |
