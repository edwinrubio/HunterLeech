# Project Research Summary

**Project:** HunterLeech — Colombian Anticorruption Graph Platform
**Domain:** Public procurement transparency / anticorruption civic tech / graph-based government data
**Researched:** 2026-04-09
**Confidence:** HIGH

## Executive Summary

HunterLeech is a graph-based public procurement intelligence platform targeting Colombian investigative journalists, veedurias, and ONGs. The canonical reference implementation is br/acc (World-Open-Graph/br-acc), a production-validated Brazilian equivalent with 45 ETL pipelines against Socrata-style open government APIs. The recommended approach is a strict four-layer pipeline: Socrata SODA API extraction → Python ETL normalization → Neo4j graph database → FastAPI REST API consumed by a React frontend. This architecture is proven at scale for this exact domain, avoids unnecessary infrastructure complexity, and enables a Docker Compose deployment that journalists can self-host without cloud expertise.

The platform's defining technical choice is Neo4j 5.26 LTS as the graph store, with Cypher pattern matching as the query language for detecting procurement fraud networks. The frontend differentiator is WebGL-based graph visualization via @react-sigma/core (Sigma.js v3), which handles the 10,000+ node scale of full Colombian contractor networks — unlike Canvas-based alternatives. The ETL stack uses Polars over pandas for memory-efficient processing of SECOP's millions of rows, and httpx over the deprecated sodapy library for async Socrata API calls. The entire v1 stack runs in three Docker containers (Neo4j, FastAPI, Nginx) with no Redis, no Celery, and no message broker.

The primary risks are not technical but domain-specific: entity resolution treated as an afterthought permanently corrupts the graph; Colombian Ley 1581/2012 (habeas data) compliance must be baked in from day one, not retrofitted; and graph visualizations that imply guilt without source attribution create legal liability under Colombian defamation law. The mitigation strategy is clear: establish the entity resolution model, privacy gate architecture, and Neo4j schema constraints before loading any data, and design the UI around investigation workflows discovered through journalist user research rather than around what the data makes technically possible.

## Key Findings

### Recommended Stack

The stack is well-validated against both the br/acc reference project and Colombian open data infrastructure. All version pins are current as of April 2026. Neo4j 5.26 LTS is preferred over the newer calendar-versioned 2025.x/2026.x releases specifically because LTS stability matters for a civic tool journalists will deploy independently over multiple years. The Python driver is `neo4j` (v6.1.0) — not the deprecated `neo4j-driver` package. Polars 1.39.x replaces pandas for the ETL hot path given SECOP's million-row scale. APScheduler replaces Celery/Airflow for nightly batch scheduling — correct for a six-source sequential workload that does not warrant a message broker.

**Core technologies:**

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Graph DB | Neo4j Community | 5.26 LTS | Primary store; Cypher pattern matching; APOC + GDS plugins |
| Backend | FastAPI + Uvicorn | 0.135.3 | Async REST API; auto-generates OpenAPI docs |
| Backend | Python | 3.12 | Runtime (performance gains over 3.11; 3.13 too new) |
| Backend | neo4j driver | 6.1.0 | Async Bolt connection to Neo4j |
| Backend | Pydantic | v2 | Validation (5-50x faster than v1; required for large SECOP payloads) |
| ETL | Polars | 1.39.3 | DataFrame processing (3-10x faster than pandas, lower memory) |
| ETL | httpx | latest | Async Socrata SODA API client (replaces deprecated sodapy) |
| ETL | APScheduler | 3.x | Nightly cron scheduling (embedded in FastAPI; no broker needed) |
| Frontend | React + TypeScript | 19.x / 5.x | UI framework with compile-time type safety for graph data models |
| Frontend | @react-sigma/core | 5.0.6 | WebGL graph visualization (handles 10,000+ nodes; Sigma.js v3) |
| Frontend | graphology | 0.25.x | Graph data structure layer required by Sigma.js v3 |
| Frontend | TanStack Query | 5.x | Server state and API data fetching |
| Frontend | Tailwind CSS | 4.x | Utility-first styling |
| Frontend | Vite | 8.x | Build tool |
| Infra | Docker Compose | v2 | Single-command deployment; three services only |
| Infra | Nginx | 1.27.x | Reverse proxy + static frontend serving |

### Expected Features

The feature set is divided clearly by research into what journalists need on day one (table stakes), what makes HunterLeech distinct from PACO (differentiators), and what should be explicitly deferred to avoid scope creep.

**Must have (table stakes) — v1:**
- Entity search by NIT, cedula, and nombre (fuzzy matching required; Colombian data has typos) — users arrive with an identifier and leave if they can't find it immediately
- Contractor profile page aggregating contracts, sanctions, and related entities in one view
- Contract detail view with SECOP fields (valor, entidad, modalidad, plazo, numero_oferentes)
- Sanctions flags from SIRI (Procuraduria) and Boletin Responsables Fiscales (Contraloria) — missing this makes the platform dangerous
- Automated SECOP + SIRI ingestion via Socrata SODA API with incremental updates
- Per-source data freshness indicator (trust depends on visible recency)
- Privacy-safe defaults enforcing Ley 1581/2012 compliance
- Spanish-language interface
- Docker Compose reproducible local deployment

**Should have (differentiators) — v2:**
- Graph relationship visualization (WebGL, interactive, zoomable) — core differentiator vs. PACO's list UI
- Cross-source entity linking (same cedula person across SIGEP, RUES, SECOP)
- Red flag / pattern detection engine: single bidder, short tender window, direct award concentration, sanctioned contractor with active contract
- Public REST API with OpenAPI docs and rate limiting
- Per-source audit trail with provenance metadata on every data point

**Defer (v3+):**
- Conflict of interest detection (requires both SIGEP and RUES integrated)
- Newly-created company flag (requires RUES integration)
- Cypher query access for advanced users
- Concentration analysis dashboards
- Benford's law deviation detection
- International sanctions data sources (OFAC, EU)

**Explicit anti-features — never build:**
- Guilt scores or corruption rankings (legal liability, methodologically indefensible)
- Scraped data without API (fragile, legally ambiguous)
- Crowdsourced / user-submitted data (moderation burden, defamation risk)
- ML-based entity resolution (Colombian data has cedula/NIT as reliable deterministic keys)
- Mobile application (out of scope; responsive web sufficient for desktop-heavy journalist workflow)

### Architecture Approach

The architecture follows a strict unidirectional pipeline: external Socrata APIs feed per-source ETL modules that populate Neo4j via idempotent MERGE-based upserts, which FastAPI exposes as a read-only REST API consumed by the React frontend. The hard rule is layered isolation: ETL writes directly to Neo4j; FastAPI never calls ETL; frontend never touches Neo4j. The reference implementation is br/acc — directory layout, Docker Compose structure, FastAPI route organization, and Neo4j schema are directly reusable as templates.

**Major components:**

1. **ETL Layer (Python/Polars/httpx)** — per-source pipeline modules following Extract → Normalize → Deduplicate → Load pattern; writes to Neo4j via batched UNWIND MERGE statements; runs on APScheduler cron or as a standalone Docker profile
2. **Neo4j Graph Database** — stores nodes (Persona, Empresa, EntidadPublica, Contrato, Proceso, Sancion) and relationships (ADJUDICO, EJECUTA, REPRESENTA, EMPLEA, SANCIONO, PARTICIPO); uniqueness constraints on NIT, cedula, id_contrato required before first data load
3. **FastAPI Backend** — translates REST requests to Cypher queries; enforces privacy gate (PUBLIC_MODE env var blocks Persona node exposure); service layer owns all Cypher (no Cypher in route handlers); lifespan dependency injection for Neo4j async session
4. **React Frontend** — search bar → entity list → graph explorer (react-sigma WebGL) → entity detail panel with source provenance; TanStack Query for server state
5. **Docker Compose / Nginx** — three services: neo4j, api, frontend; Nginx serves Vite build artifacts and proxies /api/ to FastAPI; no Redis, no Celery worker

**Key graph schema patterns:**
- Store categorical values (municipio, sector, tipo_contrato) as node properties, not as separate nodes — avoiding super nodes with 500K+ relationships
- MERGE nodes separately before MERGE-ing relationships (full pattern MERGE causes duplicates)
- Tag every record with `fuente` (source dataset ID) for lineage and audit trail
- Batch writes in chunks of 500-1,000 via UNWIND; one batch = one transaction

### Critical Pitfalls

1. **Entity resolution deferred** — Retroactive deduplication of millions of nodes with attached relationships is extremely expensive and propagates errors transitively. Solve before any MERGE statements: normalize NIT (strip leading zeros, remove hyphens), use cedula as primary key for persons, handle null/empty NITs as sentinels not merged nodes. Use Splink for name-only matching as fallback. Address in Phase 1.

2. **SECOP I and SECOP II treated as the same schema** — They have different field names, identifier formats, and contracting stage semantics. Write separate ETL pipelines per dataset; use dataset ID as mandatory provenance property; add a cross-SECOP deduplication step keyed on NIT + numero_contrato + entidad_nit. Address in Phase 1.

3. **Super nodes from categorical values** — Connecting millions of contracts to a single Bogota node or single "Prestacion de Servicios" node creates 500K+ relationship nodes that make all traversals unusable. Store categoricals as properties on Contrato nodes. Address in Phase 1 schema design.

4. **Graph visualization implying guilt** — Every relationship must display source, date, and semantic meaning. No aggregate suspicion scores. Prominent disambiguation for common names. Mandatory "Reportar error" mechanism. Legal disclaimer required before public deployment. Address in Phase 2 (graph model) and Phase 4 (frontend).

5. **Ley 1581/2012 scope misapplied** — Conduct a field classification inventory (PUBLICA / SEMIPRIVADA / PRIVADA / SENSIBLE) before ingesting any dataset. Do not store personal email, home address, or personal phone. PUBLIC_MODE=true as default deployment flag. Cannot be retrofitted after data is exposed. Address in Phase 1 (data modeling) and Phase 3 (API design).

6. **Socrata offset pagination gaps** — New records inserted mid-crawl shift offsets, silently skipping records. Sort all queries by a stable field; use `$where=fecha_de_cargue > '{last_run_timestamp}'` for incremental updates; implement post-load count reconciliation. Address in Phase 1.

7. **Missing Neo4j constraints before first load** — MERGE without a unique constraint causes full label scans; at 1M nodes a 20-minute pipeline becomes 48 hours. Run `schema.cypher` (constraints on nit, cedula, id_contrato, id_sancion) before any ETL. Address in Phase 1 infra setup.

## Implications for Roadmap

Dependencies flow strictly upward — each layer requires the layer below to be stable. Research strongly indicates that parallelizing ETL and API development before the graph schema is proven will cause expensive schema churn.

### Phase 1: Foundation — Infra, Schema, and First ETL Pipeline

**Rationale:** Everything else depends on Neo4j being reachable with correct constraints and at least one proven dataset loaded. This phase establishes the entity resolution strategy, privacy model, and data pipeline pattern that all subsequent phases replicate. Getting schema wrong here is the most expensive mistake in the project.
**Delivers:** Running Docker Compose stack; Neo4j with constraints and indexes; field classification inventory per dataset; entity resolution strategy documented and tested; SECOP Integrado ETL pipeline loading real data; idempotent pipeline with offset-stable pagination and incremental update logic
**Addresses features:** Automated data ingestion, per-source data freshness indicator, Docker Compose local deployment
**Avoids pitfalls:** Entity resolution afterthought (P1), SECOP schema confusion (P2), super nodes (P3), missing constraints (P6), Socrata pagination gaps (P5), Ley 1581 misapplication (P7), RUES/Contraloria source type conflation (P12)
**Research flag:** NEEDS DEEPER RESEARCH — field classification inventory requires reviewing each Socrata dataset's schema against Ley 1581 categories before any ingestion logic is written

### Phase 2: Core ETL — Remaining Sources and Graph Population

**Rationale:** Schema is proven from Phase 1. The per-source pipeline pattern is repeatable. Load remaining five datasets (SECOP II contratos, SECOP II procesos, SECOP multas, SIRI sanciones, SIGEP servidores) before building the API on top, so the API serves real linked data.
**Delivers:** All six Socrata sources ingested; cross-source entity linking via cedula/NIT; provenance metadata on every node; super node audit check added to CI; sanctions nodes linked to contractor nodes
**Addresses features:** Cross-source entity linking (foundational), sanctions flags (data side), audit trail metadata
**Avoids pitfalls:** SECOP I/II schema confusion (separate pipelines), super node accumulation (monthly audit query)
**Research flag:** STANDARD PATTERNS — pipeline structure from Phase 1 repeats; no novel research needed

### Phase 3: FastAPI Backend — Search, Entity Detail, and Privacy Gate

**Rationale:** Data is loaded and linked. API unblocks frontend development and provides the testable interface for validating data quality. Privacy gate must be built before any public-facing endpoint is exposed.
**Delivers:** `/api/v1/search`, `/api/v1/graph/{id}`, `/api/v1/meta`, `/health` endpoints; Pydantic response models; PUBLIC_MODE privacy middleware; OpenAPI docs auto-generated; query depth cap (depth=2) and 30-second timeout enforced
**Addresses features:** Entity search by identifier, contract detail view, contractor profile page (data side), per-source freshness indicator (API side)
**Avoids pitfalls:** Raw Persona node exposure (privacy gate), unbounded subgraph queries (depth cap + timeout), ETL writing through API (separation of concerns)
**Research flag:** STANDARD PATTERNS — FastAPI + Neo4j async pattern is well-documented via br/acc and prrao87/neo4j-python-fastapi

### Phase 4: React Frontend — Search, Entity Detail, and Spanish UI

**Rationale:** API is stable. Build the search-first UI that delivers the table stakes journalist workflow before adding graph visualization complexity. Conduct journalist user research before sprint planning to define the five concrete investigation stories.
**Delivers:** Spanish-language search interface; contractor profile page; contract detail view; sanctions flags displayed prominently; data freshness indicator; source provenance on every data point; "Reportar error" mechanism; legal disclaimer copy; Docker-hosted frontend via Nginx
**Addresses features:** All nine table stakes features from the MVP list
**Avoids pitfalls:** Graph visualization implying guilt (provenance UI built into base layer, not added later), user adoption failure (journalist user research gates sprint planning)
**Research flag:** NEEDS USER RESEARCH before sprint planning — three journalist/veeduria interviews and five documented investigation stories required; PACO interface review required to understand existing user mental models

### Phase 5: Graph Visualization — Interactive Network Explorer

**Rationale:** Base search and detail views work and have been validated with real users. Graph visualization is the core differentiator but also the highest complexity component. Adding it after baseline functionality means schema is proven, data quality is validated, and user workflows are understood.
**Delivers:** WebGL force-directed graph explorer (@react-sigma/core); clickable nodes with entity detail sidebar; relationship tooltips with source and date; neighborhood highlighting; zoom and pan; configurable depth (default depth=2 for public); relationship type color coding
**Addresses features:** Graph relationship visualization (primary differentiator vs. PACO)
**Avoids pitfalls:** Canvas renderer performance ceiling (WebGL via Sigma.js handles 10K+ nodes), browser crash from super nodes (graph depth cap enforced at API level)
**Research flag:** STANDARD PATTERNS — @react-sigma v5 + graphology v0.25 patterns are documented; force-atlas2 layout is standard for this domain

### Phase 6: Pattern Detection and Public API

**Rationale:** All data sources are loaded and entity linking is proven. Pattern detection requires cross-source data and stable entity model. Public API ships after data model is stable to avoid breaking consumers.
**Delivers:** P0 red flags (single bidder, short tender period, direct award concentration, sanctioned contractor with active contract); offline batch pattern execution (not synchronous API); `/api/v1/patterns` endpoint (feature-flagged); public REST API with rate limiting and OpenAPI docs; GDS Community centrality scoring (PageRank, Betweenness) for "most connected" contractor ranking
**Addresses features:** Red flag / pattern detection engine, public REST API, concentration analysis
**Avoids pitfalls:** Complex Cypher OOM in production (offline batch only; test at 500K+ contract volume before shipping; GDS for graph algorithms), Cypher query complexity unbounded (30-second timeout in neo4j.conf)
**Research flag:** NEEDS DEEPER RESEARCH — GDS Community algorithm configuration for Colombian contractor graph scale; pattern detection query profiling at realistic data volume before sprint commitment

### Phase Ordering Rationale

- **Schema first, API second, UI third** is the strict dependency chain dictated by the br/acc architecture. Violating this order causes schema churn that propagates through all layers.
- **Entity resolution in Phase 1** (not "later") is the single most important sequencing decision. The PITFALLS research is explicit: retroactive deduplication of a populated graph is extremely expensive and error-propagating.
- **Privacy gate in Phase 3** (before any public endpoint) is required by Ley 1581/2012. It cannot be retrofitted.
- **Graph visualization in Phase 5** (after search/detail UX is validated) prevents building the complex WebGL component on top of unvalidated data quality.
- **Pattern detection in Phase 6** (after all sources loaded) prevents building cross-source analysis on incomplete data.

### Research Flags

Needs deeper research during planning:
- **Phase 1:** Field classification inventory for each Socrata dataset against Ley 1581/2012 categories — requires reviewing actual dataset schemas, not just assuming public record status
- **Phase 4:** Journalist user research — three interviews minimum, five documented investigation stories — required before frontend sprint planning begins
- **Phase 6:** GDS Community algorithm configuration for graph scale; pattern detection query profiling at 500K+ contract volume before sprint commitment

Standard patterns (skip research-phase):
- **Phase 2:** ETL pipeline pattern repeats from Phase 1; no novel integration
- **Phase 3:** FastAPI + Neo4j async pattern well-documented; br/acc is direct template
- **Phase 5:** @react-sigma v5 + graphology patterns documented; force-atlas2 layout is standard

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All major version pins verified against PyPI, npm, and official docs as of April 2026; br/acc provides direct production validation |
| Features | HIGH | Cross-validated against PACO (Colombian reference), br/acc (direct reference), OCCRP Aleph, Open Contracting Partnership 73-indicator taxonomy |
| Architecture | HIGH | br/acc directly inspected; Neo4j, FastAPI, and Socrata patterns verified via official documentation; component boundaries and data flow are standard for this domain |
| Pitfalls | HIGH | Mix of official sources (Neo4j docs, Ley 1581 text, OCDS quality guide, Socrata pagination docs) and high-confidence practitioner sources (ICIJ methodology, Harvard Ash Center research, br/acc README) |

**Overall confidence:** HIGH

### Gaps to Address

- **RUES data access:** RUES (company registry) requires institutional credentials and has no free API. The "newly-created company" and "conflict of interest" features depend on it. Plan RUES integration as a stub adapter in Phase 2 and resolve credential access separately — do not block the MVP on it.
- **Contraloria Boletin Fiscal format:** The Boletin de Responsables Fiscales is a quarterly PDF, not a Socrata API. A specific PDF parser pipeline is needed. Treat as a separate source type (Type B: bulk download + parse) and implement in Phase 2 with an explicit "last parsed date" alert if stamp is more than 90 days old.
- **SECOP field semantics:** The official "Manual para el uso de Datos Abiertos del SECOP" (Colombia Compra Eficiente, 2024) must be consulted before any field mapping in Phase 1. Do not infer semantics from column names alone — SECOP I and SECOP II share column names with different meanings.
- **Neo4j Community backup:** Community Edition has no hot backup. Cold backup via `neo4j-admin dump` must be scheduled and tested before any public deployment. If high availability becomes a hard requirement post-MVP, evaluate AuraDB or Enterprise.
- **sodapy deprecation confirmation:** Research assessed sodapy as effectively deprecated (ownership transfer March 2025, max Python 3.10 declared support) but there is no official deprecation notice. httpx is still the correct choice; flag for reassessment if sodapy ownership produces a new release.

## Sources

### Primary (HIGH confidence)
- [br/acc GitHub — World-Open-Graph/br-acc](https://github.com/World-Open-Graph/br-acc) — direct architecture reference; ETL structure, Docker Compose, FastAPI organization, Neo4j schema
- [Neo4j end-of-life and version table](https://endoflife.date/neo4j) — LTS version verification
- [Neo4j Python Driver 6.1 docs](https://neo4j.com/docs/api/python-driver/current/) — async driver API
- [FastAPI PyPI](https://pypi.org/project/fastapi/) — version 0.135.3 verified
- [Polars PyPI](https://pypi.org/project/polars/) — version 1.39.3 verified
- [neo4j PyPI](https://pypi.org/project/neo4j/) — version 6.1.0 verified
- [@react-sigma/core npm](https://www.npmjs.com/package/@react-sigma/core) — version 5.0.6 verified
- [Vite 8 announcement](https://vite.dev/blog/announcing-vite8) — version 8.x confirmed
- [Open Contracting Partnership — Red Flags guide](https://www.open-contracting.org/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/) — 73-indicator taxonomy
- [Ley 1581 de 2012 — Gestor Normativo Función Pública](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981) — Colombian habeas data law
- [Neo4j: Graph Modeling — All About Super Nodes](https://medium.com/neo4j/graph-modeling-all-about-super-nodes-d6ad7e11015b) — super node anti-pattern
- [Neo4j Entity Resolution GitHub Examples](https://github.com/neo4j-graph-examples/entity-resolution) — entity resolution patterns
- [Harvard Ash Center: Transparency is Insufficient](https://ash.harvard.edu/articles/transparency-is-insufficient-lessons-from-civic-technology-for-anticorruption/) — civic tech failure modes
- [ICIJ: Three Key Lessons from Managing the Biggest Journalism Projects](https://www.icij.org/investigations/pandora-papers/three-key-lessons-from-managing-the-biggest-journalism-projects-in-history/) — journalism platform methodology
- [Socrata SODA Consumer API](https://dev.socrata.com/consumers/getting-started.html) — extraction and pagination patterns
- [MERGE clause — Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/clauses/merge/) — idempotent upsert patterns
- [Colombia Compra Eficiente — Manual de Datos Abiertos SECOP 2024](https://www.colombiacompra.gov.co/wp-content/uploads/2024/09/manual_de_datos_abiertos_actualizado.pdf) — SECOP field semantics
- [Splink — Probabilistic Record Linkage](https://moj-analytical-services.github.io/splink/index.html) — name-only entity resolution fallback
- [Neo4j GDS Community centrality algorithms](https://neo4j.com/docs/graph-data-science/current/algorithms/centrality/) — PageRank/Betweenness without Enterprise license

### Secondary (MEDIUM confidence)
- [HTTPX async docs](https://www.python-httpx.org/async/) — async Socrata client rationale
- [sodapy GitHub](https://github.com/afeld/sodapy) — deprecation evidence (ownership transfer, Python 3.10 ceiling)
- [Polars vs Pandas 2025 benchmark](https://www.shuttle.dev/blog/2025/09/24/pandas-vs-polars) — 3-10x speedup validation
- [APScheduler vs Celery comparison](https://leapcell.io/blog/scheduling-tasks-in-python-apscheduler-vs-celery-beat) — scheduling architecture rationale
- [PACO Portal Anticorrupcion Colombia](https://portal.paco.gov.co/) — Colombian incumbent feature benchmark
- [OCP Latin America red flags study](https://www.open-contracting.org/2019/06/27/examining-procurement-red-flags-in-latin-america-with-data/) — Colombia-specific red flag validation
- [FastAPI + Neo4j integration pattern — prrao87](https://github.com/prrao87/neo4j-python-fastapi) — async session dependency injection pattern
- [EGOS-Inteligencia — 83.7M node public data graph](https://github.com/enioxt/EGOS-Inteligencia) — scale reference for Colombian context

---
*Research completed: 2026-04-09*
*Ready for roadmap: yes*
