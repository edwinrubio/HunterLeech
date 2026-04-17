# Roadmap: HunterLeech

## Overview

HunterLeech goes from zero to a publicly deployable anticorruption graph platform in four phases. The dependency chain is strict: infrastructure and graph schema must be proven before ETL pipelines are multiplied; all sources must be loaded before the API can serve real linked data; and the API must be stable before the frontend and pattern detection are built on top of it. The four phases follow this chain and deliver a complete, self-hostable v1 in the fewest steps possible.

## Phases

- [x] **Phase 1: Foundation** - Docker Compose stack running, Neo4j schema with constraints, privacy model established, and first ETL pipeline loading real SECOP data (completed 2026-04-10)
- [x] **Phase 2: Full ETL** - All five remaining Socrata sources ingested, cross-source entity linking by cedula/NIT, provenance metadata on every node (completed 2026-04-10)
- [x] **Phase 3: Backend API** - FastAPI search, profile, contract, and graph endpoints with privacy gate enforcing Ley 1581/2012 (completed 2026-04-10)
- [x] **Phase 4: Frontend and Pattern Detection** - Spanish-language search UI, contractor profiles, contract detail, interactive graph visualization, and red flag detection (completed 2026-04-10)

## Phase Details

### Phase 1: Foundation
**Goal**: A reproducible local stack is running with the correct graph schema, privacy model established, and at least one real ETL pipeline loading SECOP data into Neo4j
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, PRIV-01, ETL-01, ETL-07, ETL-08
**Success Criteria** (what must be TRUE):
  1. Running `docker compose up` brings up Neo4j, FastAPI, and Nginx with no errors
  2. Neo4j has uniqueness constraints on cedula, NIT, id_contrato, and id_sancion before any data loads
  3. Every dataset field is classified as PUBLICA, SEMIPRIVADA, PRIVADA, or SENSIBLE in a documented inventory before ingestion begins
  4. The SECOP Integrado pipeline loads real records with provenance metadata (fuente, timestamp, URL) attached to every node
  5. Re-running the pipeline produces no duplicate nodes (MERGE-based idempotence verified)
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Docker Compose stack (neo4j, api, nginx) + Neo4j schema constraints
- [x] 01-02-PLAN.md — Privacy field classification (PRIV-01) + NIT/cedula normalizer (INFRA-03)
- [x] 01-03-PLAN.md — SECOP Integrado ETL pipeline with provenance and idempotent MERGE

### Phase 2: Full ETL
**Goal**: All six Socrata sources are ingested, entities are linked across sources by cedula and NIT, and every node carries provenance metadata
**Depends on**: Phase 1
**Requirements**: ETL-02, ETL-03, ETL-04, ETL-05, ETL-06
**Success Criteria** (what must be TRUE):
  1. SECOP II Contratos, SIGEP, SIRI, and SECOP Multas pipelines load data without schema errors
  2. A person found in SIGEP as a public official also appears linked to their SECOP contracts via cedula
  3. Sancion nodes from SIRI are linked to the corresponding Persona or Empresa node in the graph
  4. No categorical value (municipio, sector, tipo_contrato) exists as a node with more than 10,000 relationships
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — SECOP II Contratos pipeline (SecopIIContratosPipeline, three-pass MERGE)
- [x] 02-02-PLAN.md — SIGEP + SIRI + Multas pipelines + run.py registry (entity linking implicit via MERGE)
- [x] 02-03-PLAN.md — Schema index + verification script + human sign-off on cross-source linking

### Phase 3: Backend API
**Goal**: FastAPI exposes search, profile, contract detail, and graph traversal endpoints with a privacy gate blocking protected personal data in public mode
**Depends on**: Phase 2
**Requirements**: API-01, API-02, API-03, API-04, API-05, API-06, API-07, PRIV-02, PRIV-03
**Success Criteria** (what must be TRUE):
  1. A search by NIT, cedula, or name returns matching entities with fuzzy matching handling common Colombian typos
  2. A contractor profile response includes their contracts, active sanctions, and related entities in one API call
  3. Graph traversal queries are capped at depth=2 and a 30-second timeout, preventing runaway Cypher execution
  4. With PUBLIC_MODE=true, no protected personal fields (email, home address, personal phone) appear in any API response
  5. Each API response includes a freshness indicator showing when each source was last ingested
**Plans**: TBD

### Phase 4: Frontend and Pattern Detection
**Goal**: Investigators can search for any entity, view their procurement network, see red flags, and trace every data point to its source — all in Spanish
**Depends on**: Phase 3
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08, PAT-01, PAT-02, PAT-03, PAT-04, PAT-05
**Success Criteria** (what must be TRUE):
  1. A user can type a NIT, cedula, or name and land on a contractor profile page showing contracts, sanctions, and red flags
  2. Red flag badges (single bidder, short tender window, inflated contract, direct award concentration, sanctioned contractor) appear on relevant records
  3. The interactive WebGL graph explorer renders the procurement network around any entity and allows clicking nodes to navigate
  4. Every data point on screen shows its source and ingestion date, with no bare assertions of relationships
  5. The entire interface is in Spanish and renders correctly on desktop viewport widths
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete    | 2026-04-10 |
| 2. Full ETL | 3/3 | Complete    | 2026-04-10 |
| 3. Backend API | 3/3 | Complete    | 2026-04-10 |
| 4. Frontend and Pattern Detection | 3/3 | Complete    | 2026-04-10 |
