# Phase 2: Full ETL - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning
**Source:** User deferred all gray areas to Claude's discretion

<domain>
## Phase Boundary

Ingest 4 remaining Socrata datasets (SECOP II Contratos, SIGEP, SIRI, SECOP Multas) and cross-link entities across all sources by cedula and NIT. Every node must carry provenance metadata. No categorical value node may exceed 10,000 relationships.

</domain>

<decisions>
## Implementation Decisions

### Entity Linking
- Deterministic matching by cedula (personas) and NIT (empresas) — no fuzzy matching needed
- Reuse normalize_nit() and normalize_cedula() from etl/normalizers/common.py (Phase 1)
- MERGE on normalized keys ensures automatic linking when same entity appears in multiple sources
- Records with null/invalid identifiers are skipped (null sentinel policy from Phase 1)

### Super Node Prevention
- Categorical values (municipio, departamento, sector, tipo_contrato, modalidad) stored as node properties, NOT as separate nodes with relationships
- This avoids the super node problem entirely — no categorical node can accumulate relationships
- If a categorical query is needed, use Neo4j indexes on properties instead

### Pipeline Execution Order
- SECOP II Contratos first (extends existing contract graph)
- SIGEP second (adds public servants, links to contracts by cedula)
- SIRI third (adds sanctions, links to persons/companies by cedula/NIT)
- SECOP Multas last (adds fines, links to existing contractors)
- Cross-linking happens implicitly via MERGE on shared keys — no separate linking step needed

### Pipeline Pattern
- All new pipelines extend BasePipeline from etl/base.py (Phase 1 pattern)
- Same three-pass MERGE pattern: entities first, then relationships
- Same provenance metadata (fuente, ingested_at, url_fuente) on every node
- Same incremental state via etl/state.py

### Claude's Discretion
- Field mapping for each new dataset (inspect actual API responses)
- Batch sizes and pagination strategy per source
- Error handling for malformed records
- Dataset-specific normalization beyond NIT/cedula

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 Implementation (reuse patterns)
- `etl/base.py` — BasePipeline abstract class
- `etl/sources/secop_integrado.py` — Reference pipeline implementation
- `etl/normalizers/common.py` — Shared normalization functions
- `etl/loaders/neo4j_loader.py` — Neo4j loader with constraint verification
- `etl/config.py` — ETL configuration
- `etl/state.py` — Run state persistence
- `infra/neo4j/schema.cypher` — Graph schema constraints

### Data Sources
- SECOP II Contratos: `https://www.datos.gov.co/resource/jbjy-vk9h.json`
- SIGEP Servidores Publicos: `https://www.datos.gov.co/resource/2jzx-383z.json`
- SIRI Sanciones: `https://www.datos.gov.co/resource/iaeu-rcn6.json`
- SECOP Multas y Sanciones: `https://www.datos.gov.co/resource/4n4q-k399.json`

</canonical_refs>

<specifics>
## Specific Ideas

- Follow the exact same pattern as secop_integrado.py for each new pipeline
- Super node criterion from ROADMAP: no categorical node with > 10,000 relationships

</specifics>

<deferred>
## Deferred Ideas

None — phase scope is clear.

</deferred>

---

*Phase: 02-full-etl*
*Context gathered: 2026-04-10 via discuss-phase (user deferred to defaults)*
