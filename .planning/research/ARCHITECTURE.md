# Architecture Patterns: Graph-Based Public Data Transparency Platform

**Domain:** Anticorruption public data intelligence platform
**Researched:** 2026-04-09
**Confidence:** HIGH — primary reference (br/acc) directly inspected; Neo4j, FastAPI, and Socrata patterns verified via official documentation

---

## Recommended Architecture

The canonical architecture for this class of system follows a unidirectional pipeline: external public APIs feed ETL workers that populate a graph database, which is then exposed via a REST API consumed by a React frontend and external programmatic clients.

```
┌─────────────────────────────────────────────┐
│            External Data Sources            │
│  datos.gov.co Socrata SODA API (6 datasets) │
│  RUES / Contraloria / PACO (future)         │
└──────────────────┬──────────────────────────┘
                   │ HTTP (paginated JSON)
                   ▼
┌─────────────────────────────────────────────┐
│              ETL Layer (Python)             │
│  Per-source pipeline modules                │
│  Extract → Normalize → Deduplicate → Load   │
│  Runs on schedule (cron) or one-shot        │
└──────────────────┬──────────────────────────┘
                   │ Cypher MERGE (Bolt)
                   ▼
┌─────────────────────────────────────────────┐
│         Neo4j Graph Database                │
│  Nodes: Persona, Empresa, Entidad,          │
│         Contrato, Proceso, Sancion          │
│  Rels:  ADJUDICO, REPRESENTA, SANCIONO,     │
│         PARTICIPO, EMPLEO                   │
└───────────┬─────────────────────────────────┘
            │ Bolt (async driver)
            ▼
┌─────────────────────────────────────────────┐
│         FastAPI Backend (Python)            │
│  /api/v1/search  — entity lookup            │
│  /api/v1/graph   — subgraph by ID/NIT       │
│  /api/v1/patterns — suspicious pattern scan │
│  /api/v1/meta    — source health + counts   │
│  /health         — liveness probe           │
└──────────┬──────────────────────────────────┘
           │ HTTP/JSON (REST)
           ▼
┌─────────────────────────────────────────────┐
│         React + TypeScript Frontend         │
│  Search bar → entity result list            │
│  Graph explorer (react-force-graph / Cyto)  │
│  Entity detail panel                        │
│  Filters: date, value, institution, dept.   │
└─────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Does NOT own | Communicates with |
|-----------|---------------|--------------|-------------------|
| ETL modules (per-source) | Fetch, normalize, deduplicate, upsert raw data into Neo4j | Query logic, API routing, UI | Neo4j (write only) |
| Neo4j | Store graph; execute Cypher traversals and pattern queries | HTTP, business rules, presentation | ETL (inbound writes), FastAPI (inbound reads) |
| FastAPI | Translate REST requests into Cypher queries; enforce privacy gates; serialize responses | ETL scheduling, graph storage, UI rendering | Neo4j (read, occasionally write audit log) |
| React frontend | Render search UI, graph visualization, entity detail views | Backend logic, data storage | FastAPI REST API only |
| Docker Compose / infra | Container orchestration, networking, environment config | Application logic | All services |

**Hard rule:** ETL writes directly to Neo4j. FastAPI never calls ETL. Frontend never touches Neo4j. Components communicate only through the next layer in the pipeline.

---

## Neo4j Graph Schema

### Node Labels

| Label | Identifier | Key Properties |
|-------|-----------|---------------|
| `Persona` | `cedula` or `nombre_normalizado` | `nombre`, `cargo`, `entidad_empleadora`, `fuente` |
| `Empresa` | `nit` | `razon_social`, `tipo`, `fecha_constitucion`, `municipio`, `fuente` |
| `EntidadPublica` | `codigo_entidad` | `nombre`, `nivel` (nacional/departamental/municipal), `sector` |
| `Contrato` | `id_contrato` | `valor`, `fecha_inicio`, `fecha_fin`, `objeto`, `modalidad`, `fuente` |
| `Proceso` | `referencia_proceso` | `tipo`, `estado`, `valor_estimado`, `entidad_compradora` |
| `Sancion` | `id_sancion` | `tipo`, `fecha`, `autoridad`, `descripcion`, `fuente` |

### Relationship Types

| Relationship | From → To | Key Properties | Source |
|-------------|-----------|---------------|--------|
| `ADJUDICO` | `EntidadPublica` → `Contrato` | `fecha`, `modalidad` | SECOP |
| `EJECUTA` | `Empresa` → `Contrato` | `rol` (ejecutor/subcontratista) | SECOP |
| `PARTICIPO` | `Empresa` → `Proceso` | `resultado` (ganador/no_ganador) | SECOP II Procesos |
| `REPRESENTA` | `Persona` → `Empresa` | `cargo`, `fecha_inicio`, `fecha_fin` | SIGEP / RUES |
| `EMPLEA` | `EntidadPublica` → `Persona` | `cargo`, `nivel`, `desde` | SIGEP |
| `SANCIONO` | `Persona|Empresa` → `Sancion` | `autoridad` | SIRI / SECOP Multas |
| `RELACIONADO_CON` | `Empresa` → `Empresa` | `tipo_relacion` | RUES (future) |

### Idempotency Pattern

All ETL writes use Neo4j `MERGE` to guarantee idempotent upserts — re-running a pipeline produces the same final state without duplicates.

```cypher
// Canonical ETL upsert pattern
MERGE (e:Empresa {nit: $nit})
ON CREATE SET e.razon_social = $razon_social,
              e.fecha_constitucion = $fecha_constitucion,
              e.fuente = $fuente,
              e.created_at = datetime()
ON MATCH SET  e.razon_social = $razon_social,
              e.updated_at = datetime()

MERGE (c:Contrato {id_contrato: $id_contrato})
ON CREATE SET c.valor = $valor, c.objeto = $objeto, c.fuente = $fuente

MERGE (e)-[:EJECUTA]->(c)
```

**Critical:** MERGE nodes separately before MERGE-ing relationships. Merging full patterns (node + relationship in one MERGE) causes duplicates when parts already exist.

---

## Data Flow

### 1. Extraction (Socrata SODA API)

Each pipeline module follows the same pattern:

```
GET https://www.datos.gov.co/resource/{DATASET_ID}.json
    ?$limit=1000
    &$offset={page * 1000}
    &$$app_token={TOKEN}

→ paginate until response < $limit rows
→ yield batches of 1,000 records
```

Rate limit: ~1,000 req/hour with token. Pagination is mandatory — datasets range from tens of thousands to millions of rows.

### 2. Normalization (ETL Transform)

Each source gets its own normalizer. Common transforms:
- Strip/normalize whitespace in NIT, cedula, nombre fields
- Lowercase + unidecode entity names for fuzzy deduplication key
- Parse currency values (remove "." thousands separators, handle null)
- Map source-specific status codes to canonical vocabulary
- Tag every record with `fuente` (source dataset ID) for lineage

### 3. Graph Load (Neo4j Write)

- Use the official `neo4j` Python driver (async) with connection pooling
- Batch writes: send records in chunks of 500–1,000 via `UNWIND $batch AS row MERGE ...`
- Transaction scope: one batch = one transaction. Failure rolls back the batch, not the whole pipeline.
- Constraint enforcement: unique constraints on `nit`, `cedula`, `id_contrato`, etc., must be created before first load.

### 4. API Query (FastAPI → Neo4j)

```
Client request → FastAPI route handler
  → validate + sanitize input
  → inject Neo4j async session (via lifespan dependency)
  → execute Cypher query
  → serialize result to Pydantic model
  → return JSON response

Privacy gate (PUBLIC_MODE env var):
  → block Persona node exposure
  → restrict subgraph depth on sensitive nodes
  → omit fields tagged as habeas_data=true
```

### 5. Frontend Rendering

```
Search query → GET /api/v1/search?q={term}&type={empresa|persona|entidad}
  → entity list with match scores

Entity selection → GET /api/v1/graph/{id}?depth=2
  → nodes[] + edges[] (graph JSON)
  → react-force-graph renders force-directed layout
  → click node → sidebar panel with entity detail
  → click edge → relationship metadata tooltip
```

---

## FastAPI Structure

```
api/
├── main.py              # app factory, lifespan (DB connect/disconnect)
├── config.py            # settings from env vars (pydantic-settings)
├── dependencies.py      # Neo4j session dependency injection
├── routers/
│   ├── search.py        # GET /api/v1/search
│   ├── graph.py         # GET /api/v1/graph/{id}
│   ├── patterns.py      # GET /api/v1/patterns (feature-flagged)
│   └── meta.py          # GET /api/v1/meta, /health
├── services/
│   ├── search_service.py    # Cypher query logic for search
│   ├── graph_service.py     # Subgraph retrieval queries
│   └── pattern_service.py   # Pattern detection queries
├── models/
│   ├── entities.py      # Pydantic models for nodes
│   └── graph.py         # GraphResponse, NodeDTO, EdgeDTO
└── privacy.py           # PUBLIC_MODE filtering middleware
```

**Key pattern:** Route handlers call service functions. Service functions own the Cypher. No Cypher in route handlers. This makes queries testable in isolation.

---

## ETL Structure

```
etl/
├── base.py              # BasePipeline abstract class (extract/transform/load interface)
├── config.py            # Socrata tokens, Neo4j URI, batch sizes
├── sources/
│   ├── secop_integrado.py   # Dataset rpmr-utcd
│   ├── secop_ii_contratos.py  # Dataset jbjy-vk9h
│   ├── secop_ii_procesos.py   # Dataset p6dx-8zbt
│   ├── secop_multas.py        # Dataset 4n4q-k399
│   ├── siri_sanciones.py      # Dataset iaeu-rcn6
│   └── sigep_servidores.py    # Dataset 2jzx-383z
├── normalizers/
│   ├── common.py        # Shared field cleaning (NIT, names, currency)
│   └── per_source.py    # Source-specific field mapping
├── loaders/
│   └── neo4j_loader.py  # MERGE batch writer, constraint setup
└── run.py               # CLI entrypoint (run one source or all)
```

---

## Infra / Docker Compose Structure

```
infra/
├── docker-compose.yml   # Service definitions
├── neo4j/
│   ├── schema.cypher    # Constraints + indexes (run once on first boot)
│   └── seed/            # Demo data for local dev
└── .env.example         # Environment variable template

Services:
  neo4j      → port 7474 (HTTP browser), 7687 (Bolt)
  api        → port 8000, depends_on neo4j
  frontend   → port 3000, proxies /api to api service
  etl        → optional profile, exits after run
```

Neo4j constraints to create before first load:
```cypher
CREATE CONSTRAINT empresa_nit IF NOT EXISTS
  FOR (e:Empresa) REQUIRE e.nit IS UNIQUE;

CREATE CONSTRAINT persona_cedula IF NOT EXISTS
  FOR (p:Persona) REQUIRE p.cedula IS UNIQUE;

CREATE CONSTRAINT contrato_id IF NOT EXISTS
  FOR (c:Contrato) REQUIRE c.id_contrato IS UNIQUE;

CREATE CONSTRAINT sancion_id IF NOT EXISTS
  FOR (s:Sancion) REQUIRE s.id_sancion IS UNIQUE;
```

---

## Suggested Build Order

Dependencies flow strictly upward — each layer depends on the layer below it being stable.

| Phase | Component | Why First |
|-------|-----------|-----------|
| 1 | Infra skeleton (Docker Compose, Neo4j boot, schema constraints) | Everything else depends on Neo4j being reachable |
| 2 | ETL for one source (SECOP Integrado — richest dataset) | Validates data model before building API on top |
| 3 | Neo4j schema refinement (indexes, query profiling) | Query performance must be established before API |
| 4 | FastAPI core (search + subgraph endpoints) | Provides testable interface; unblocks frontend |
| 5 | React search + entity detail (no graph viz yet) | Validates data quality with real UI before adding complexity |
| 6 | Graph visualization component | Adds most complexity; base functionality must work first |
| 7 | Remaining ETL sources (5 remaining Socrata datasets) | Schema proven; pipeline pattern repeatable |
| 8 | Pattern detection endpoints + privacy gates | Cross-source analysis needs all data loaded; privacy review last |

**Critical dependency:** Neo4j schema constraints must be created before any ETL runs. Running ETL before constraints risks duplicate nodes that are expensive to merge later.

**Do not parallelize:** ETL development and API development can be parallelized after Phase 2, because the schema is stable. Before that, concurrent work risks schema churn.

---

## Scalability Considerations

| Concern | MVP (dev/local) | Small deployment (1K users) | Larger deployment |
|---------|-----------------|----------------------------|-------------------|
| Neo4j sizing | Community, single node, 8GB RAM | Community, 16GB RAM, SSD | Enterprise or AuraDB for HA |
| ETL frequency | Manual / cron nightly | Nightly cron via Docker scheduler | Apache Airflow or Prefect for orchestration |
| API concurrency | Single FastAPI worker | 2–4 uvicorn workers | Add nginx, scale horizontally |
| Graph query depth | Allow depth=3 | Profile and cap at depth=2 for public API | Add query timeout enforcement |
| Rate limiting | None | nginx rate limit on /api | Dedicated API gateway |

For HunterLeech MVP: single Docker Compose node with Neo4j Community is sufficient. The graph will be small enough (millions of nodes, not billions) for a 16GB machine to handle queries comfortably.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Merging Full Patterns in One MERGE

**What:** `MERGE (e:Empresa)-[:EJECUTA]->(c:Contrato {id: $id})`
**Why bad:** If the Empresa exists but the Contrato does not, Neo4j creates a new Empresa duplicate instead of matching the existing one.
**Instead:** MERGE each node separately, then MERGE the relationship.

### Anti-Pattern 2: Unbounded Subgraph Queries

**What:** `MATCH (n)-[*]-(m) WHERE n.nit = $nit RETURN *`
**Why bad:** On a dense graph, this traverses millions of paths and times out or OOMs.
**Instead:** Always cap depth (`[*..2]`) and limit results (`LIMIT 500`). Add query timeout in driver config.

### Anti-Pattern 3: ETL Writing Directly Through the API

**What:** Frontend triggers ETL refresh via a FastAPI endpoint that runs Python ingestion inline.
**Why bad:** Mixes concerns, blocks the API thread, no retry logic, no audit trail.
**Instead:** ETL runs independently (cron or separate container). API is read-only.

### Anti-Pattern 4: Skipping Constraints Before First Load

**What:** Running ETL pipelines before creating uniqueness constraints.
**Why bad:** MERGE without a unique constraint does full graph scan; duplicate nodes are created under concurrent writes.
**Instead:** `infra/neo4j/schema.cypher` runs on first boot before any ETL.

### Anti-Pattern 5: Exposing Raw Persona Nodes Without Privacy Gate

**What:** `/api/v1/graph/{cedula}` returns full Persona subgraph including employment and salary.
**Why bad:** Violates Ley 1581/2012 (habeas data) for public deployments.
**Instead:** `PUBLIC_MODE=true` blocks Persona node resolution. Investigation features are opt-in per deployment.

---

## Reference Architecture Source

The br/acc project (World-Open-Graph/br-acc) implements this identical pattern with 45 ETL modules against Brazilian public data. Directory layout, Docker Compose structure, FastAPI route organization, and Neo4j schema approach are directly reusable as templates for HunterLeech. Primary differences: dataset IDs, field names, and the legal framework (LGPD → Ley 1581/2012).

---

## Sources

- [br/acc GitHub — World-Open-Graph/br-acc](https://github.com/World-Open-Graph/br-acc) — direct architecture reference (HIGH confidence)
- [Neo4j Python Driver Async API](https://neo4j.com/docs/api/python-driver/current/async_api.html) — official docs (HIGH confidence)
- [MERGE clause — Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/clauses/merge/) — official docs (HIGH confidence)
- [Graph Databases for Journalists — Neo4j Developer Blog](https://medium.com/neo4j/graph-databases-for-journalists-5ac116fe0f54) — procurement graph data model (MEDIUM confidence)
- [Exploring €1.3 trillion in public contracts — Linkurious](https://linkurious.com/blog/exploring-e1-3-trillion-in-public-contracts-with-graph-visualization/) — procurement visualization patterns (MEDIUM confidence)
- [react-force-graph — vasturiano](https://vasturiano.github.io/react-force-graph/) — graph viz library (HIGH confidence)
- [Socrata SODA Consumer API](https://dev.socrata.com/consumers/getting-started.html) — extraction pattern (HIGH confidence)
- [FastAPI + Neo4j integration pattern — prrao87/neo4j-python-fastapi](https://github.com/prrao87/neo4j-python-fastapi) — FastAPI/Neo4j async pattern (MEDIUM confidence)
- [EGOS-Inteligencia — Neo4j public data graph, 83.7M nodes](https://github.com/enioxt/EGOS-Inteligencia) — scale reference for Colombian context (MEDIUM confidence)
