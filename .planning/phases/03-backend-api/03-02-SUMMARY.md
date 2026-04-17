---
phase: 03-backend-api
plan: "02"
subsystem: api
tags: [contractor-profile, contract-detail, neo4j-aggregation, privacy, rate-limiting, pagination]
dependency_graph:
  requires:
    - 03-01 (PrivacyFilter, APIResponse envelope, freshness_service, get_neo4j_session, get_privacy_filter)
  provides:
    - GET /api/v1/contractor/{id} — full Empresa or Persona profile with contracts, sanctions, related entities
    - GET /api/v1/contract/{id} — contract detail with entidad, ejecutor, and competing oferentes
    - contractor_service.get_contractor_profile() — NIT->Empresa or cedula->Persona aggregation
    - contract_service.get_contract_detail() — contract detail with Proceso/PARTICIPO oferentes
  affects:
    - api/main.py (two new routers registered under /api/v1)
tech_stack:
  added: []
  patterns:
    - Two-query aggregation pattern: count query (no LIMIT) for totals + paginated data query
    - SKIP/LIMIT pagination on contracts ordered by fecha_inicio DESC
    - filter_node("Persona", ...) applied at every Persona property set extraction point
    - Separate Proceso query to avoid Cartesian product with PARTICIPO oferentes
    - ejecutor_tipo discriminator field ("Empresa" | "Persona" | null) for type-safe UI consumption
key_files:
  created:
    - api/services/contractor_service.py
    - api/services/contract_service.py
    - api/routers/contractors.py
    - api/routers/contracts.py
  modified:
    - api/main.py
decisions:
  - "Two-query pattern for Empresa profile: separate count query (no LIMIT) guarantees contratos_total accuracy regardless of page; avoids COUNT(*) + SKIP/LIMIT in single query which would give wrong totals"
  - "Persona profile does not paginate empresas_representadas (capped at 50) — investigators typically represent fewer companies than large Empresa contractors have contracts"
  - "Proceso + oferentes fetched in second query to avoid Cartesian product inflation of contract row count in single OPTIONAL MATCH chain"
  - "ejecutor_tipo explicit discriminator field chosen over duck-typing on ejecutor properties for reliable frontend type switching"
metrics:
  duration: "~2 minutes"
  completed_date: "2026-04-10"
  tasks_completed: 3
  files_changed: 5
---

# Phase 3 Plan 02: Contractor Profile and Contract Detail Endpoints Summary

**One-liner:** Cypher aggregation services for Empresa/Persona contractor profiles (paginated contracts + sanctions + related entities) and contract detail (entidad + ejecutor + PARTICIPO oferentes), exposed as GET /api/v1/contractor/{id} and GET /api/v1/contract/{id} with rate limiting and privacy filtering.

## What Was Built

### Task 1: Contractor Profile Service (`api/services/contractor_service.py`)

`get_contractor_profile(id, session, privacy, page, page_size)` resolves NIT or cedula automatically:

**Empresa path** (NIT match):
1. Count query: `MATCH (e:Empresa {nit})-[:EJECUTA]->(c:Contrato) RETURN count(c)` — no LIMIT, gives accurate `contratos_total`
2. Paginated contracts: `SKIP $skip LIMIT $page_size ORDER BY c.fecha_inicio DESC` with OPTIONAL MATCH for adjudicating entidad
3. Sanctions: `MATCH (e)-[:SANCIONO]->(s:Sancion)` ordered by date DESC, LIMIT 50
4. Representatives: `MATCH (p:Persona)-[r:REPRESENTA]->(e)` with `filter_node("Persona", rep)` applied to each

Returns: `{tipo, empresa, contratos, contratos_total, sanciones, representantes}`

**Persona path** (cedula match):
1. Persona node fetched and immediately filtered: `filter_node("Persona", dict(persona_record["p"]))`
2. Represented companies: `MATCH (p)-[r:REPRESENTA]->(e:Empresa)` with fuente, ORDER BY fecha_inicio DESC, LIMIT 50
3. Employing entities: `MATCH (entidad:EntidadPublica)-[r:EMPLEA]->(p)` LIMIT 20
4. Sanctions: `MATCH (p)-[:SANCIONO]->(s:Sancion)` LIMIT 50

Returns: `{tipo, persona, empresas_representadas, empleadores, sanciones}`

Both paths return `None` when entity not found.

### Task 2: Contract Detail Service (`api/services/contract_service.py`)

`get_contract_detail(id_contrato, session, privacy)` uses two queries:

**Query 1** — Main contract record:
```cypher
MATCH (c:Contrato {id_contrato: $id_contrato})
OPTIONAL MATCH (entidad:EntidadPublica)-[:ADJUDICO]->(c)
OPTIONAL MATCH (ejecutor:Empresa)-[:EJECUTA]->(c)
OPTIONAL MATCH (ejecutor_persona:Persona)-[:EJECUTA]->(c)
```
`filter_node("Persona", ...)` applied to `ejecutor_persona` when present.

**Query 2** — Associated Proceso and PARTICIPO oferentes:
```cypher
MATCH (c:Contrato {id_contrato: $id_contrato})
OPTIONAL MATCH (c)-[:GENERADO_DE]->(p:Proceso)
OPTIONAL MATCH (oferente:Empresa)-[part:PARTICIPO]->(p)
RETURN collect(DISTINCT {nit, razon_social, resultado}) AS oferentes
```
Null-nit entries filtered out (handles case where Proceso exists but no competing oferentes).

Returns: `{contrato, entidad, ejecutor, ejecutor_tipo, proceso}`

### Task 3: Routers and main.py Registration

**`api/routers/contractors.py`** — GET /api/v1/contractor/{id}:
- `@limiter.limit("30/minute")` — heavier aggregation query
- `page_size = min(page_size, 100)` cap enforced in handler
- HTTP 404 when `get_contractor_profile()` returns None
- Returns `APIResponse[dict]` with freshness metadata

**`api/routers/contracts.py`** — GET /api/v1/contract/{id}:
- `@limiter.limit("60/minute")` — simpler node lookup
- HTTP 404 when `get_contract_detail()` returns None
- Returns `APIResponse[dict]` with freshness metadata

**`api/main.py`** updated — added two imports and `include_router` calls under `/api/v1` prefix. Lifespan, app factory, and limiter setup unchanged.

## Privacy Filtering Points

All Persona property sets are filtered through `privacy.filter_node("Persona", ...)`:

| Location | When applied |
|----------|-------------|
| `contractor_service._get_empresa_profile()` | Each representante in REPRESENTA results |
| `contractor_service._get_persona_profile()` | Persona node itself |
| `contract_service.get_contract_detail()` | ejecutor when Persona executes contract |

With `PUBLIC_MODE=true`: `email`, `telefono_personal`, `direccion_residencia`, `fecha_nacimiento`, `numero_documento` absent from all Persona dicts.

## Pagination Strategy

Contractor contracts use two-query pagination:
- Query 1: `count(c)` with no LIMIT — always accurate total regardless of page
- Query 2: `SKIP (page-1)*page_size LIMIT page_size ORDER BY fecha_inicio DESC`
- Default page_size=100, max capped at 100 in router handler

Large contractors (e.g., 5,000+ contracts) receive accurate `contratos_total` count while only paying bandwidth cost for one page.

## Verification Results

All automated checks passed:

```
contractor_service.py: get_contractor_profile exported           PASS
contractor_service.py: contratos_total present                   PASS
contractor_service.py: filter_node called                        PASS
contract_service.py: get_contract_detail exported                PASS
contract_service.py: ADJUDICO relationship queried               PASS
contract_service.py: PARTICIPO relationship queried              PASS
main.py: contractors_router registered                           PASS
main.py: contracts_router registered                             PASS
contractors.py: @limiter.limit("30/minute")                      PASS
contracts.py: @limiter.limit("60/minute")                        PASS
```

Live stack verification (requires `docker compose up -d` + data loaded) not run — no running Neo4j instance with data available in this execution environment.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. Both endpoints return real Neo4j query results. Empty arrays (`contratos: []`, `sanciones: []`) are correct behavior when an entity has no associated records — not stubs.

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | c87809c | feat(03-02): add contractor profile service |
| 2 | 85c2891 | feat(03-02): add contract detail service |
| 3 | 9c5ed10 | feat(03-02): add contractor and contract routers, register in main.py |
