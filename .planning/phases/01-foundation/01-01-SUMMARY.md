---
phase: 01-foundation
plan: 01
subsystem: infra
tags: [neo4j, fastapi, docker, docker-compose, nginx, python, cypher, pydantic-settings]

# Dependency graph
requires: []
provides:
  - Docker Compose three-service topology (neo4j, api, nginx)
  - Neo4j 5.26.24-community running with APOC plugin mount
  - 6 uniqueness constraints + 4 supporting indexes in schema.cypher
  - FastAPI skeleton with /health endpoint and async Neo4j driver lifecycle
  - pydantic-settings config from environment variables
  - scripts/apply-schema.sh for idempotent schema application
affects:
  - 01-02 (ETL pipeline depends on Neo4j being up with constraints in place)
  - 01-03 (API endpoints depend on FastAPI skeleton and Neo4j driver pattern)
  - All subsequent phases (docker-compose.yml is the deployment contract)

# Tech tracking
tech-stack:
  added:
    - neo4j:5.26.24-community (graph database)
    - FastAPI 0.135.3 (REST API)
    - neo4j Python driver 6.1.0 (async Bolt client)
    - pydantic-settings (env var config)
    - nginx:1.27-alpine (reverse proxy)
    - python:3.12-slim (API container base)
    - polars 1.39.3 (ETL DataFrame library, added to requirements)
    - httpx (async HTTP client, added to requirements)
    - apscheduler (ETL scheduling, added to requirements)
  patterns:
    - FastAPI lifespan context manager for driver open/close
    - AsyncGraphDatabase.driver with connection pool (max 50, lifetime 3600s)
    - get_neo4j_session dependency injection via FastAPI Depends
    - Docker Compose service_healthy condition for api->neo4j startup ordering
    - IF NOT EXISTS on all Cypher DDL for idempotent re-runs

key-files:
  created:
    - docker-compose.yml
    - .env.example
    - infra/neo4j/schema.cypher
    - infra/neo4j/plugins/.gitkeep
    - api/main.py
    - api/config.py
    - api/dependencies.py
    - api/routers/health.py
    - api/routers/__init__.py
    - api/Dockerfile
    - api/requirements.txt
    - frontend/Dockerfile
    - frontend/nginx.conf
    - scripts/apply-schema.sh
  modified: []

key-decisions:
  - "Schema applied via scripts/apply-schema.sh (manual on first boot); Phase 2 will automate constraint verification at ETL startup"
  - "infra/neo4j volume mounted at /var/lib/neo4j/import/infra so cypher-shell --file can reach schema.cypher inside container"
  - "FastAPI /health executes RETURN 1 AS ok against Neo4j — single endpoint serves both liveness and DB connectivity"
  - "PUBLIC_MODE env var included in docker-compose.yml to control Ley 1581/2012 privacy gate from Phase 3 onward"

patterns-established:
  - "Pattern: All Cypher DDL uses IF NOT EXISTS for idempotent constraint/index creation"
  - "Pattern: FastAPI route handlers import from dependencies.py (get_neo4j_session) — no direct driver access in routes"
  - "Pattern: pydantic-settings BaseSettings reads from .env file and environment (docker-compose env: block)"

requirements-completed: [INFRA-01, INFRA-02]

# Metrics
duration: 2min
completed: 2026-04-10
---

# Phase 1 Plan 01: Docker Compose Infrastructure + FastAPI Skeleton Summary

**Neo4j 5.26.24 + FastAPI 0.135.3 three-service Docker Compose stack with 6 uniqueness constraints and async /health endpoint**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-10T01:18:44Z
- **Completed:** 2026-04-10T01:20:57Z
- **Tasks:** 2
- **Files modified:** 14 created

## Accomplishments

- Three-service Docker Compose topology: neo4j with APOC + healthcheck, api with service_healthy ordering, nginx proxying /api/ to FastAPI
- 6 uniqueness constraints (IF NOT EXISTS, idempotent) for all entity labels: Empresa, Persona, Contrato, Proceso, Sancion, EntidadPublica
- FastAPI skeleton with async Neo4j driver lifecycle in lifespan context manager and /health endpoint verifying DB connectivity
- scripts/apply-schema.sh helper for applying schema to a running container via cypher-shell

## Task Commits

Each task was committed atomically:

1. **Task 1: Docker Compose stack + environment template** - `a3d64b3` (chore)
2. **Task 2: Neo4j schema constraints + FastAPI skeleton** - `ef90283` (feat)

## Files Created/Modified

- `docker-compose.yml` - Three-service topology with neo4j:5.26.24-community, api, nginx:1.27-alpine
- `.env.example` - Required env var template (NEO4J_PASSWORD, SOCRATA_APP_TOKEN, PUBLIC_MODE)
- `infra/neo4j/schema.cypher` - 6 uniqueness constraints + 4 supporting indexes, all IF NOT EXISTS
- `infra/neo4j/plugins/.gitkeep` - Tracks plugins volume mount directory in git
- `api/main.py` - FastAPI app factory with lifespan and async Neo4j driver management
- `api/config.py` - pydantic-settings BaseSettings reading from .env and environment
- `api/dependencies.py` - get_neo4j_session async generator for FastAPI dependency injection
- `api/routers/health.py` - GET /health executing RETURN 1 AS ok against Neo4j
- `api/routers/__init__.py` - Empty package init
- `api/Dockerfile` - python:3.12-slim with curl, uvicorn entrypoint
- `api/requirements.txt` - Pinned: fastapi==0.135.3, neo4j==6.1.0, polars==1.39.3
- `frontend/Dockerfile` - Placeholder multi-stage build (Phase 4 will populate with React)
- `frontend/nginx.conf` - Nginx server block proxying /api/ to api:8000, SPA fallback
- `scripts/apply-schema.sh` - Runs cypher-shell inside running neo4j container to apply schema

## Decisions Made

- Schema application is a manual step on first boot via `./scripts/apply-schema.sh`. Phase 2 ETL will add automated constraint verification at startup to prevent running without constraints.
- The neo4j container volume mounts `./infra/neo4j` at `/var/lib/neo4j/import/infra` so cypher-shell's `--file` flag can reach `schema.cypher` from inside the container.
- FastAPI /health endpoint executes a live Cypher query (`RETURN 1 AS ok`) rather than a static response, so it serves double duty as both liveness probe and Neo4j connectivity check.
- The `PUBLIC_MODE` environment variable is wired into docker-compose.yml from the start, even though the privacy gate logic is implemented in Phase 3. This prevents breaking API changes at that point.

## Deviations from Plan

None - plan executed exactly as written.

The plan already included the `./infra/neo4j:/var/lib/neo4j/import/infra` volume mount (described in Task 2 action), so this was incorporated directly into docker-compose.yml during Task 1 creation.

## Issues Encountered

None.

## User Setup Required

Before running `docker compose up`, copy the environment template:

```bash
cp .env.example .env
# Edit .env and set a real NEO4J_PASSWORD
```

After the stack starts (neo4j needs ~60s on first boot):

```bash
./scripts/apply-schema.sh
```

This applies the 6 uniqueness constraints and 4 indexes. Re-running is safe (IF NOT EXISTS).

Verification:
```bash
curl http://localhost:8000/health
# expects: {"status":"ok","neo4j":"connected"}

curl http://localhost:80/api/health
# same response via Nginx proxy
```

## Next Phase Readiness

- Docker Compose stack is the foundation for all subsequent plans
- Neo4j schema constraints must be applied before Plan 02 (ETL) can run
- FastAPI skeleton with dependency injection pattern is ready for Plan 03 route expansion
- The `api/requirements.txt` already includes polars, httpx, and apscheduler for Plan 02 ETL work

## Self-Check: PASSED

All 13 created files verified present on disk. Both task commits (a3d64b3, ef90283) verified in git log.

---
*Phase: 01-foundation*
*Completed: 2026-04-10*
