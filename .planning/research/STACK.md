# Technology Stack

**Project:** HunterLeech — Colombian Anticorruption Graph Platform
**Researched:** 2026-04-09
**Confidence:** HIGH (all major choices verified against current PyPI, npm, and official docs)

---

## Recommended Stack

### Graph Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Neo4j Community Edition | 5.26 LTS | Primary graph store for entity-relationship data | LTS release (supported until June 2028) gives stability for a multi-year civic platform. The 2025/2026 calendar-versioned releases are newer but rolling and not LTS. Community Edition is GPLv3, sufficient for this open-source project. Cypher is the dominant query language for graph pattern matching — exactly what "find networks of related contractors" requires. |

**Why not 2025.x/2026.x?** Neo4j switched to calendar-based versioning in 2025 with monthly releases. None carry LTS status. For a reproducible civic tool that journalists will deploy independently, LTS is worth more than bleeding-edge features. Cypher 5 (what 5.26 uses) is fully sufficient.

**Why not alternatives (Memgraph, ArangoDB, FalkorDB)?** Neo4j 5 has the largest Python driver ecosystem, the most APOC procedure coverage, and direct alignment with the br/acc reference project. FalkorDB is faster but has a tiny community. ArangoDB's multi-model is overkill; the domain is purely relational-graph.

**Plugins to install:**
- APOC Core (bundled in `labs/` directory in Docker image) — needed for data import helpers, string normalization on NIT/cedula values, and merge-on-conflict upsert patterns
- Graph Data Science (GDS) Community — centrality algorithms (PageRank, Betweenness) to score "most connected" contractors and officials without an Enterprise license

### Backend

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12 | Runtime | 3.12 is the current stable with performance gains over 3.11 (5-15% faster). 3.13 is too new for ecosystem maturity. |
| FastAPI | 0.135.x | REST API for graph queries and entity search | Async-native (ASGI), auto-generates OpenAPI docs (critical for a "public API" requirement), Python type hints drive both validation and docs. Direct br/acc pattern match. Latest stable: 0.135.3. |
| Uvicorn | latest | ASGI server | Standard FastAPI deployment pairing. Use `uvicorn[standard]` for production. |
| neo4j (driver) | 6.1.x | Neo4j Python driver | Version 6.1.0 is current stable (January 2026). Note: the old `neo4j-driver` package is deprecated; install `neo4j` instead. Supports Neo4j 5.x and 2025.x servers. Requires Python >=3.10. |
| Pydantic | v2 | Request/response validation | FastAPI uses Pydantic v2 natively. Do not use v1 — v2 is 5-50x faster on validation, which matters for large SECOP contract payloads. |

### ETL Pipeline

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Polars | 1.39.x | DataFrame processing for ingest + transform | 3-10x faster than pandas on 1M+ row datasets with 30-60% lower memory. Colombian SECOP datasets are large (SECOP Integrado has millions of rows). Lazy evaluation means pipeline runs don't OOM. Use instead of pandas for the hot path. |
| httpx | latest | Async HTTP client for Socrata API calls | Async-native (asyncio), HTTP/2 support, built-in retry patterns. Replaces `requests` (sync-only) and `sodapy` (sync, stale, minimal Python version support). Direct SODA API calls via `https://www.datos.gov.co/resource/{ID}.json` with `$limit`, `$offset`, `$where` SoQL params are trivial with httpx. |
| APScheduler | 3.x | Cron-style scheduling for nightly ingestion | Lightweight, no broker required (unlike Celery which needs Redis/RabbitMQ). In-process scheduling is correct here — ETL jobs are sequential by source, not massively parallel. One scheduler embedded in the FastAPI app or a standalone `scheduler` container. |

**Why not sodapy?** `sodapy` version 2.2.0 (last substantive update) only declares support for Python <=3.10. Its underlying `requests` library is synchronous. For a platform that needs to paginate millions of SECOP rows efficiently, raw `httpx` with `asyncio` concurrency across multiple Socrata endpoints is the right approach. Ownership transferred in March 2025 indicates it is not actively evolved.

**Why not pandas?** Pandas is appropriate for notebooks and small datasets. For production ETL with 1M+ contract rows and nightly batch runs, Polars' memory efficiency and speed are material. The one exception: if a specific algorithm only exists in a pandas-dependent library (e.g., scikit-learn), use `polars.to_pandas()` at that point in the pipeline only.

**Why not Celery/Airflow/Prefect?** Celery requires a message broker (Redis or RabbitMQ) — that's two extra Docker containers for a use case (nightly batch, ~6 sources) that APScheduler handles in-process. Prefect/Airflow add DAG orchestration complexity appropriate for data engineering teams, not a two-person civic tech project.

### Frontend

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| React | 19.x | UI framework | Current stable. React 19 compiler optimizations reduce re-render cost, relevant for large graph visualizations where node/edge counts change frequently. |
| TypeScript | 5.x | Type safety | Required — graph data models (Node, Relationship, Properties) need compile-time correctness. |
| Vite | 8.x | Build tool | Current stable. Vite 8 uses Oxc for React Refresh (no Babel dependency, faster HMR). Standard choice for React+TS in 2025-2026. |
| @react-sigma/core | 5.0.x | Graph visualization | Wraps Sigma.js v3 (WebGL renderer) in idiomatic React components. WebGL is mandatory for graphs with 1000+ nodes — SVG/Canvas (D3, react-force-graph) degrade at that scale. `@react-sigma/layout-forceatlas2` (v5.0.6) provides force-directed layout suitable for network exploration. |
| graphology | 0.25.x | Graph data structure | Sigma.js v3 requires graphology as its graph model layer. Provides node/edge traversal, serialization, and import/export utilities. |
| TanStack Query | 5.x | Server state / API data fetching | Standard for React REST data fetching. Handles caching, background refresh, and loading states for graph query results. |
| React Router | 6.x | Client-side routing | Stable, file-based routing for search pages, entity detail views, graph explorer. |
| Tailwind CSS | 4.x | Styling | Zero-runtime, utility-first. Tailwind 4 has native CSS variables and faster builds. No component library needed — the UI is primarily the graph canvas + search inputs. |

**Why @react-sigma over react-force-graph?** Both are actively maintained. The decision is the renderer: `react-force-graph` uses Canvas (2D) which struggles above ~2,000 nodes. `@react-sigma` uses WebGL, which handles 10,000+ nodes smoothly. Colombian public contractor networks will be large. Sigma.js is also the library used by investigative journalism graph tools (OCCRP Aleph, etc.) — domain alignment.

**Why not Cytoscape.js?** Cytoscape is Canvas-based and has performance limits at 10K+ nodes. Its React integration (`react-cytoscapejs`) is less actively maintained than the @react-sigma ecosystem.

**Why not D3 directly?** D3 is a low-level primitive. Building interactive graph exploration from scratch on D3 adds 2-4 weeks of engineering for features that Sigma/graphology already provide (hover, click, neighborhood highlight, zoom). Use D3 only for secondary charts (e.g., contract value histograms).

### Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker | latest stable | Container runtime | Standard. |
| Docker Compose | v2 | Local dev + deployment orchestration | Reproducible single-command deployment for journalists self-hosting. Matches br/acc pattern. |
| Nginx | 1.27.x (alpine) | Reverse proxy + static frontend serving | Termination point for HTTP; serves Vite build artifacts; proxies `/api/` to FastAPI. No need for a cloud load balancer in v1. |

**Service topology (docker-compose):**
```
nginx          :80/:443  -> proxies API to fastapi, serves React static
fastapi        :8000     -> REST API + APScheduler
neo4j          :7474/:7687 -> graph database
```

No Redis, no Celery worker, no separate scheduler container in v1. APScheduler runs inside the FastAPI process. If ETL runtime grows beyond 30 minutes nightly, extract to a separate `etl` service calling the same Neo4j instance.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Graph DB | Neo4j 5.26 LTS | Memgraph | Memgraph is faster but has smaller Python ecosystem and no APOC equivalent; br/acc already validated Neo4j |
| Graph DB | Neo4j 5.26 LTS | FalkorDB | Open-source Redis module; minimal tooling for graph algorithms; not production-proven for civic platforms |
| Graph DB | Neo4j 5.26 LTS | ArangoDB | Multi-model adds complexity; Cypher vs AQL matters — journalists familiar with Cypher due to Neo4j's dominance |
| Backend | FastAPI | Django REST | Django is heavier, sync-first; FastAPI's async is better for concurrent Socrata API calls |
| Backend | FastAPI | Flask | No async, no auto-docs; inferior for a "public REST API" requirement |
| ETL | Polars | pandas | Slower, higher memory on large SECOP datasets; pandas still appropriate for ML integration points |
| ETL HTTP | httpx | sodapy | sodapy is sync-only, max Python 3.10, not actively evolved |
| ETL HTTP | httpx | aiohttp | httpx has cleaner API, better HTTP/2 support, easier testing (respx mock library) |
| Scheduling | APScheduler | Celery | Celery requires Redis broker; overkill for 6 sequential nightly batch jobs |
| Scheduling | APScheduler | Prefect/Airflow | Heavyweight orchestration; unsuitable for a two-container civic app |
| Graph viz | @react-sigma | react-force-graph | Canvas renderer; degrades above 2K nodes; WebGL required for full contractor networks |
| Graph viz | @react-sigma | Cytoscape.js | Canvas-based; worse performance ceiling; less active React integration |
| Graph viz | @react-sigma | D3.js | Primitive — requires 2-4 weeks of custom graph interaction code |

---

## Installation

```bash
# Backend (Python 3.12)
pip install "fastapi[standard]"==0.135.3
pip install neo4j==6.1.0
pip install polars==1.39.3
pip install httpx
pip install apscheduler

# Frontend
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install @react-sigma/core @react-sigma/layout-forceatlas2 graphology
npm install @tanstack/react-query react-router-dom
npm install -D tailwindcss @tailwindcss/vite
```

---

## Key Version Pins (April 2026)

| Package | Pinned Version | Source |
|---------|---------------|--------|
| Neo4j (DB) | 5.26 LTS | endoflife.date/neo4j |
| neo4j (Python driver) | 6.1.0 | pypi.org/project/neo4j |
| FastAPI | 0.135.3 | pypi.org/project/fastapi |
| Polars | 1.39.3 | pypi.org/project/polars |
| Sigma.js | 3.0.2 | npmjs.com/package/sigma |
| @react-sigma/core | 5.0.6 | npmjs.com/package/@react-sigma/core |
| Vite | 8.x | vite.dev/releases |

---

## Confidence Assessment

| Component | Confidence | Basis |
|-----------|------------|-------|
| Neo4j 5.26 LTS | HIGH | Verified via endoflife.date (official data) + Neo4j docs |
| neo4j Python driver 6.1.0 | HIGH | Verified via pypi.org directly |
| FastAPI 0.135.3 | HIGH | Verified via pypi.org directly |
| Polars 1.39.3 | HIGH | Verified via pypi.org directly |
| @react-sigma 5.x + Sigma.js 3 | HIGH | Verified via npm search results |
| Vite 8.x | HIGH | Verified via vite.dev official releases |
| httpx over sodapy | MEDIUM | sodapy ownership transfer + Python version ceiling sourced from GitHub; not official deprecation notice but evidence is clear |
| APScheduler over Celery | HIGH | Architectural reasoning verified by multiple sources |
| Polars over pandas for large ETL | HIGH | Multiple independent benchmarks (3-10x speedup confirmed) |

---

## Sources

- [Neo4j end-of-life and version table](https://endoflife.date/neo4j)
- [Neo4j calendar versioning blog](https://neo4j.com/blog/developer/neo4j-v5-lts-evolution/)
- [Neo4j Python Driver 6.1 docs](https://neo4j.com/docs/api/python-driver/current/)
- [neo4j PyPI](https://pypi.org/project/neo4j/)
- [FastAPI PyPI](https://pypi.org/project/fastapi/)
- [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/)
- [Polars PyPI](https://pypi.org/project/polars/)
- [Polars vs Pandas 2025 benchmark (Shuttle)](https://www.shuttle.dev/blog/2025/09/24/pandas-vs-polars)
- [Polars 25x ETL speedup case study](https://markaicode.com/polars-replace-pandas/)
- [sodapy GitHub](https://github.com/afeld/sodapy)
- [HTTPX async docs](https://www.python-httpx.org/async/)
- [Sigma.js official site](https://www.sigmajs.org/)
- [@react-sigma/core npm](https://www.npmjs.com/package/@react-sigma/core)
- [React Sigma practical guide (2025)](https://www.menudo.com/react-sigma-js-the-practical-guide-to-interactive-graph-visualization-in-react/)
- [Graph viz library comparison (Memgraph)](https://memgraph.com/blog/you-want-a-fast-easy-to-use-and-popular-graph-visualization-tool)
- [Vite 8 announcement](https://vite.dev/blog/announcing-vite8)
- [APScheduler vs Celery (Leapcell)](https://leapcell.io/blog/scheduling-tasks-in-python-apscheduler-vs-celery-beat)
- [Neo4j Docker Compose official docs](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/)
- [Neo4j APOC installation docs](https://neo4j.com/docs/apoc/current/installation/)
- [Neo4j GDS Community centrality algorithms](https://neo4j.com/docs/graph-data-science/current/algorithms/centrality/)
