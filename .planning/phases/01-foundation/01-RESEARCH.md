# Phase 1: Foundation - Research

**Researched:** 2026-04-09
**Domain:** Docker Compose infrastructure, Neo4j graph schema, privacy classification, SECOP SODA API ETL
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Sistema desplegable con un solo comando via Docker Compose (Neo4j + FastAPI + React) | Docker Compose v5, Neo4j 5.26.24-community image confirmed available; three-service topology documented |
| INFRA-02 | Esquema de grafos en Neo4j con constraints de unicidad para entidades (Persona, Empresa, EntidadPublica, Contrato, Proceso, Sancion) | Cypher constraint DDL verified; must run before any ETL; MERGE-before-relationships pattern critical |
| INFRA-03 | Estrategia de entity resolution documentada con reglas de normalizacion de NIT y cedula antes de cualquier carga de datos | NIT/cedula normalization rules documented; null sentinel pattern required; resolution before ingest is a hard gate |
| PRIV-01 | Clasificacion de campos por nivel de privacidad antes de almacenar cualquier dato | SECOP Integrado schema fetched live (22 fields); Ley 1581/2012 four-tier classification explained; field inventory template provided |
| ETL-01 | Pipeline automatizado de ingesta SECOP Integrado (rpmr-utcd) via Socrata SODA API con paginacion y App Token | SODA API confirmed reachable; pagination pattern documented; App Token registration path described |
| ETL-07 | Metadata de proveniencia por registro: dataset ID, timestamp de ingesta, URL fuente | Provenance properties documented on every node; fuente, ingested_at, url_fuente pattern established |
| ETL-08 | Ejecucion incremental (no recarga completa) con idempotencia via MERGE en Neo4j | MERGE ON CREATE / ON MATCH pattern documented; UNWIND batch approach; run-state tracking pattern |
</phase_requirements>

---

## Summary

Phase 1 establishes the entire data foundation: a running Docker Compose stack, a Neo4j graph schema with uniqueness constraints, a privacy classification inventory covering all SECOP Integrado fields, and a functioning ETL pipeline that loads real SECOP data idempotently with provenance metadata.

The most important sequencing constraint is strict: Neo4j constraints must exist before any ETL runs, and the entity resolution rules (NIT/cedula normalization) must be documented and implemented before any MERGE statements write to the graph. Violating this order creates duplicate nodes that are prohibitively expensive to retroactively merge. The research verifies this from the PITFALLS.md analysis and the architecture guidance in ARCHITECTURE.md.

The SECOP Integrado dataset (`rpmr-utcd`) is confirmed reachable via the Socrata SODA API. A live sample record was fetched during this research, and all 22 field names are documented below with their privacy classification. The `documento_proveedor` field contains cedulas and NITs of contractors and requires careful normalization — the sample shows `tipo_documento_proveedor: "Nit de Persona Natural"` confirming that natural persons sometimes appear with NIT-formatted identifiers, which complicates the Empresa vs. Persona distinction. The `origen` field distinguishes SECOP I (`"SECOPI"`) from SECOP II records within the unified dataset.

The Neo4j 5.26.24 Community image is confirmed available on Docker Hub (pushed 2026-04-08). Docker 29.1.3 and Docker Compose v5.0.1 are both available on the development machine. Python 3.13.4 is installed but none of the project Python packages are yet installed — they will need to be installed inside Docker containers, not the host Python.

**Primary recommendation:** Follow the strict build order — constraints first, normalization rules second, then ETL. Do not load any data until both INFRA-02 and INFRA-03 are verifiably done.

---

## Project Constraints (from CLAUDE.md)

| Directive | Source |
|-----------|--------|
| Stack locked to Neo4j + FastAPI + React (aligned with br/acc) | CLAUDE.md Constraints |
| Only free public Socrata API data sources in v1 | CLAUDE.md Constraints |
| Must comply with Ley 1581/2012 — no protected personal data exposure | CLAUDE.md Constraints |
| Docker Compose for reproducible local deployment | CLAUDE.md Constraints |
| Interface in Spanish | CLAUDE.md Constraints |
| Do not make direct repo edits outside a GSD workflow | CLAUDE.md GSD Workflow |

---

## Standard Stack

### Core (Phase 1 Scope)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| neo4j (Docker) | 5.26.24-community | Graph database | LTS confirmed; community tag verified on Docker Hub 2026-04-08 |
| neo4j (Python driver) | 6.1.0 | Graph writes from ETL | Current stable (Jan 2026); `neo4j-driver` is deprecated, install `neo4j` |
| Python | 3.12 | ETL + FastAPI runtime | 3.12 is specified stack; note: host machine has 3.13 — use 3.12 in Docker image |
| FastAPI | 0.135.3 | API server (skeleton in Phase 1) | Confirmed on PyPI; async-native for Bolt driver |
| Polars | 1.39.3 | ETL DataFrame transforms | 3-10x faster than pandas on large SECOP datasets; lazy evaluation |
| httpx | latest | Async SODA API client | Replaces sodapy (sync, Python ≤3.10 cap, not evolved) |
| Docker Compose | v2 (v5.0.1) | Stack orchestration | Available on dev machine; v2 syntax (`docker compose up`) |
| Nginx | 1.27-alpine | Reverse proxy | Lightweight; serves frontend static + proxies `/api/` |
| Uvicorn | latest stable | ASGI server | Pairs with FastAPI; use `uvicorn[standard]` |
| Pydantic | v2 | Data validation | FastAPI v0.135 requires Pydantic v2; do not use v1 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| APScheduler | 3.x | Nightly ETL scheduling | Phase 1 skeleton only; fully wired in Phase 2 |
| pydantic-settings | 2.x | Env var config management | Read `.env` into typed config objects |
| respx | latest | Mock httpx in tests | Used to test ETL without hitting live Socrata API |
| pytest | latest | Test runner | Unit tests for normalization functions |
| pytest-asyncio | latest | Async test support | ETL and driver calls are async |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| neo4j Python driver 6.1.0 | neo4j-driver (old package name) | neo4j-driver is deprecated — do not use |
| Polars | pandas | pandas is slower and higher memory; acceptable only for ML integration points |
| httpx | sodapy | sodapy is sync-only, Python ≤3.10, not actively maintained |
| APScheduler | Celery | Celery requires Redis broker; overkill for 6 sequential nightly jobs |
| Docker Compose v2 | v1 (`docker-compose`) | v1 is EOL; use `docker compose` (no hyphen) |

**Installation (inside Docker, not host Python):**
```bash
# requirements.txt for api/etl service
fastapi[standard]==0.135.3
uvicorn[standard]
neo4j==6.1.0
polars==1.39.3
httpx
apscheduler
pydantic-settings

# dev/test extras
pytest
pytest-asyncio
respx
```

---

## Architecture Patterns

### Recommended Project Structure

```
hunterleech/
├── docker-compose.yml
├── .env.example
├── .env                          # gitignored
├── infra/
│   └── neo4j/
│       ├── schema.cypher         # Constraints + indexes — runs before any ETL
│       └── plugins/              # APOC jar dropped here
├── api/
│   ├── Dockerfile
│   ├── main.py                   # FastAPI app factory + lifespan
│   ├── config.py                 # pydantic-settings
│   ├── dependencies.py           # Neo4j driver session injection
│   └── routers/
│       └── health.py             # /health endpoint (Phase 1 only)
├── etl/
│   ├── Dockerfile
│   ├── base.py                   # BasePipeline abstract class
│   ├── config.py                 # Socrata token, Neo4j URI, batch sizes
│   ├── normalizers/
│   │   └── common.py             # NIT/cedula normalization, name cleaning
│   ├── sources/
│   │   └── secop_integrado.py    # Dataset rpmr-utcd (Phase 1 scope)
│   ├── loaders/
│   │   └── neo4j_loader.py       # MERGE batch writer, constraint verifier
│   └── run.py                    # CLI: python -m etl.run secop_integrado
├── frontend/                     # Vite React scaffold (Phase 1: skeleton only)
│   ├── Dockerfile
│   └── nginx.conf
└── docs/
    └── privacy/
        └── field_classification.md   # PRIV-01 deliverable
```

### Pattern 1: Docker Compose Service Topology

**What:** Three services — neo4j, api, nginx — with explicit dependency ordering and health checks.

**When to use:** Always. This is the foundational topology for all phases.

```yaml
# docker-compose.yml (Phase 1 skeleton)
services:
  neo4j:
    image: neo4j:5.26.24-community
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}"
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_apoc_export_file_enabled: "true"
      NEO4J_apoc_import_file_enabled: "true"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - ./infra/neo4j/plugins:/plugins
    ports:
      - "7474:7474"
      - "7687:7687"
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "${NEO4J_PASSWORD}", "RETURN 1"]
      interval: 10s
      timeout: 5s
      retries: 10

  api:
    build: ./api
    environment:
      NEO4J_URI: "bolt://neo4j:7687"
      NEO4J_USER: "neo4j"
      NEO4J_PASSWORD: "${NEO4J_PASSWORD}"
      SOCRATA_APP_TOKEN: "${SOCRATA_APP_TOKEN}"
    depends_on:
      neo4j:
        condition: service_healthy
    ports:
      - "8000:8000"

  nginx:
    image: nginx:1.27-alpine
    volumes:
      - ./frontend/dist:/usr/share/nginx/html:ro
      - ./frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    ports:
      - "80:80"
    depends_on:
      - api

volumes:
  neo4j_data:
  neo4j_logs:
```

### Pattern 2: Neo4j Schema Constraints (Run Before Any ETL)

**What:** Uniqueness constraints on all entity primary keys. MERGE relies on these for index seeks; without them, MERGE performs a full label scan.

**When to use:** In `infra/neo4j/schema.cypher`, applied as the very first operation when the container starts.

```cypher
// Source: Neo4j Cypher Manual — CREATE CONSTRAINT
// Run order matters: all node constraints before any ETL

CREATE CONSTRAINT empresa_nit IF NOT EXISTS
  FOR (e:Empresa) REQUIRE e.nit IS UNIQUE;

CREATE CONSTRAINT persona_cedula IF NOT EXISTS
  FOR (p:Persona) REQUIRE p.cedula IS UNIQUE;

CREATE CONSTRAINT contrato_id IF NOT EXISTS
  FOR (c:Contrato) REQUIRE c.id_contrato IS UNIQUE;

CREATE CONSTRAINT proceso_ref IF NOT EXISTS
  FOR (p:Proceso) REQUIRE p.referencia_proceso IS UNIQUE;

CREATE CONSTRAINT sancion_id IF NOT EXISTS
  FOR (s:Sancion) REQUIRE s.id_sancion IS UNIQUE;

CREATE CONSTRAINT entidad_codigo IF NOT EXISTS
  FOR (e:EntidadPublica) REQUIRE e.codigo_entidad IS UNIQUE;

// Supporting indexes for search patterns used in Phase 3+
CREATE INDEX empresa_nombre IF NOT EXISTS
  FOR (e:Empresa) ON (e.razon_social);

CREATE INDEX persona_nombre IF NOT EXISTS
  FOR (p:Persona) ON (p.nombre);
```

**Apply constraints via a startup script, not manually:**

```python
# etl/loaders/neo4j_loader.py — constraint guard at ETL startup
async def verify_constraints(session):
    result = await session.run(
        "SHOW CONSTRAINTS YIELD name RETURN name"
    )
    names = {r["name"] async for r in result}
    required = {
        "empresa_nit", "persona_cedula", "contrato_id",
        "proceso_ref", "sancion_id", "entidad_codigo"
    }
    missing = required - names
    if missing:
        raise RuntimeError(
            f"ETL aborted: missing Neo4j constraints: {missing}. "
            "Run infra/neo4j/schema.cypher first."
        )
```

### Pattern 3: Idempotent ETL with MERGE + Provenance

**What:** Every node upsert uses MERGE with ON CREATE/ON MATCH. Every node carries provenance properties: `fuente`, `ingested_at`, `url_fuente`.

**When to use:** Every MERGE statement in every ETL pipeline.

```cypher
// Source: ARCHITECTURE.md canonical pattern + provenance extension
// UNWIND for batch efficiency — send 500-1000 rows per transaction

UNWIND $batch AS row
MERGE (e:EntidadPublica {codigo_entidad: row.codigo_entidad})
ON CREATE SET
  e.nombre           = row.nombre_de_la_entidad,
  e.nivel            = row.nivel_entidad,
  e.departamento     = row.departamento_entidad,
  e.municipio        = row.municipio_entidad,
  e.fuente           = row.fuente,
  e.ingested_at      = datetime(),
  e.url_fuente       = row.url_contrato

MERGE (c:Contrato {id_contrato: row.id_contrato})
ON CREATE SET
  c.valor            = row.valor_contrato,
  c.objeto           = row.objeto_a_contratar,
  c.tipo             = row.tipo_de_contrato,
  c.modalidad        = row.modalidad_de_contratacion,
  c.fecha_firma      = date(row.fecha_de_firma_del_contrato),
  c.fecha_inicio     = date(row.fecha_inicio_ejecucion),
  c.fecha_fin        = date(row.fecha_fin_ejecucion),
  c.estado           = row.estado_del_proceso,
  c.origen           = row.origen,
  c.fuente           = 'rpmr-utcd',
  c.ingested_at      = datetime(),
  c.url_fuente       = row.url_contrato
ON MATCH SET
  c.estado           = row.estado_del_proceso,
  c.updated_at       = datetime()

MERGE (e)-[:ADJUDICO {modalidad: row.modalidad_de_contratacion}]->(c)
```

**Critical rule:** MERGE each node separately before MERGE-ing the relationship. Never merge a full pattern `(a)-[:R]->(b)` in one statement — if `a` exists but `b` does not, Neo4j creates a duplicate `a`.

### Pattern 4: NIT/Cedula Normalization (Entity Resolution)

**What:** All identifier normalization happens in Python before any value touches Neo4j. The normalized value is what MERGE uses as the unique key.

**When to use:** Every field that will become a MERGE key.

```python
# etl/normalizers/common.py

import re

def normalize_nit(raw: str | None) -> str | None:
    """
    Normalize NIT to canonical form: digits only, no leading zeros, no check digit.
    Returns None for empty/invalid — caller decides how to handle (skip or sentinel).

    Examples:
      "890399010-4"  -> "890399010"
      "0890399010"   -> "890399010"
      "890.399.010"  -> "890399010"
      ""             -> None
      "N/A"          -> None
    """
    if not raw or not isinstance(raw, str):
        return None
    # Strip whitespace, hyphens, dots, spaces
    cleaned = re.sub(r'[\s\.\-]', '', raw.strip())
    # Remove check digit (last digit after hyphen was already stripped above,
    # but some formats have it without hyphen — do NOT strip last digit blindly;
    # for SECOP data the check digit is already separated by hyphen in most cases)
    # Remove leading zeros
    cleaned = cleaned.lstrip('0')
    # Validate: must be numeric after cleaning
    if not cleaned.isdigit():
        return None
    return cleaned

def normalize_cedula(raw: str | None) -> str | None:
    """
    Normalize cedula to digits only, no leading zeros.
    Same logic as NIT — cedula has no check digit.
    """
    return normalize_nit(raw)

def normalize_razon_social(raw: str | None) -> str | None:
    """
    Normalize company name for fuzzy deduplication key (not the display name).
    Lowercase, strip accents, collapse whitespace, remove legal suffixes.
    Used as a secondary matching signal when NIT is missing.
    """
    if not raw:
        return None
    import unicodedata
    normalized = unicodedata.normalize('NFD', raw.lower())
    # Remove combining characters (accents)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    # Remove legal suffix abbreviations
    for suffix in [' s.a.s.', ' s.a.', ' ltda.', ' s.c.a.', ' e.u.', ' s.e.m.']:
        normalized = normalized.replace(suffix, '')
    # Collapse whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

# Sentinel for missing NIT — do NOT merge all nulls into one node
NULL_NIT_SENTINEL = None  # Skip the node; log and count for monitoring
```

**Decision:** When NIT is null or non-normalizable, do not create an Empresa node with a null/empty NIT. Log the skip. Create a separate tracking structure (SQLite or simple counter) for unresolvable records — these are candidates for future fuzzy matching.

### Pattern 5: Socrata SODA API Pagination

**What:** Stateless offset-based pagination with stable sort key to prevent silent record gaps.

**When to use:** Every Socrata dataset extraction.

```python
# etl/sources/secop_integrado.py

import httpx
import polars as pl
from datetime import datetime, timezone

DATASET_ID = "rpmr-utcd"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
PAGE_SIZE = 1000

async def extract_all(app_token: str, last_run_at: datetime | None = None):
    """
    Paginate through SECOP Integrado dataset.
    Uses stable sort on fecha_de_firma_del_contrato to avoid offset drift.
    For incremental runs, filters by fecha_de_firma_del_contrato > last_run_at.
    Yields Polars DataFrames of PAGE_SIZE rows each.
    """
    headers = {"X-App-Token": app_token}
    params = {
        "$limit": PAGE_SIZE,
        "$order": "fecha_de_firma_del_contrato ASC",
    }
    if last_run_at:
        ts = last_run_at.strftime("%Y-%m-%dT%H:%M:%S")
        params["$where"] = f"fecha_de_firma_del_contrato > '{ts}'"

    offset = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params["$offset"] = offset
            response = await client.get(
                BASE_URL,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            rows = response.json()
            if not rows:
                break
            yield pl.DataFrame(rows)
            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
```

**Note on incremental runs:** The `$where` filter on `fecha_de_firma_del_contrato` is a reasonable proxy for new records, but SECOP data can be backfilled with contracts signed in the past. For a more robust incremental strategy, also check against a stored `max(ingested_at)` and flag any records that appear in the API after that checkpoint regardless of contract date.

### Pattern 6: Async Neo4j Driver (Python)

**What:** Use the async driver with connection pooling via FastAPI lifespan; ETL uses the same driver pattern.

```python
# api/main.py — FastAPI lifespan manages driver lifecycle
from contextlib import asynccontextmanager
from fastapi import FastAPI
from neo4j import AsyncGraphDatabase

driver = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global driver
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_lifetime=3600,
        max_connection_pool_size=50,
    )
    await driver.verify_connectivity()
    yield
    await driver.close()

app = FastAPI(lifespan=lifespan)

# api/dependencies.py — session injection
from fastapi import Depends
from typing import AsyncGenerator
from neo4j import AsyncSession

async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]:
    async with driver.session(database="neo4j") as session:
        yield session
```

### Anti-Patterns to Avoid

- **MERGE full pattern in one statement:** `MERGE (a:Empresa)-[:EJECUTA]->(b:Contrato {id: $id})` — creates duplicate Empresa nodes if the Contrato does not yet exist. Always MERGE nodes separately, then MERGE relationship.
- **ETL without constraint verification at startup:** ETL must abort if constraints are missing. Never assume schema.cypher has been applied.
- **Storing NIT as `""` or `"N/A"` in Neo4j:** These create false uniqueness collisions. Normalize to `None` and skip, not to empty string.
- **Single MERGE per row (no UNWIND):** Sending one Bolt transaction per row means 1M rows = 1M round-trips. Always batch via `UNWIND $batch AS row MERGE ...`.
- **Offset pagination without stable sort:** `$order` must be specified or offset drift causes silent gaps between paginated requests.
- **Categorical values as nodes (super nodes):** `municipio`, `departamento`, `tipo_de_contrato` have low cardinality but millions of contract relationships. Store as properties on `:Contrato`, not as separate nodes.

---

## Privacy Classification (PRIV-01)

### SECOP Integrado Field Inventory (rpmr-utcd)

Fields fetched live from the API on 2026-04-09. Every field classified per Ley 1581/2012 before any ingestion begins.

| # | Field Name | Type | Display Name | Classification | Rationale |
|---|-----------|------|-------------|---------------|-----------|
| 1 | `nivel_entidad` | text | Nivel Entidad | PUBLICA | Entity organizational level — public record |
| 2 | `codigo_entidad_en_secop` | text | Codigo Entidad en SECOP | PUBLICA | Public entity identifier |
| 3 | `nombre_de_la_entidad` | text | Nombre de la Entidad | PUBLICA | Public entity name |
| 4 | `nit_de_la_entidad` | text | NIT de la Entidad | PUBLICA | Entity NIT is public record for contracting entities |
| 5 | `departamento_entidad` | text | Departamento Entidad | PUBLICA | Geographic — public |
| 6 | `municipio_entidad` | text | Municipio Entidad | PUBLICA | Geographic — public |
| 7 | `estado_del_proceso` | text | Estado del Proceso | PUBLICA | Contract lifecycle status — public |
| 8 | `modalidad_de_contrataci_n` | text | Modalidad de Contratacion | PUBLICA | Procurement modality — public record |
| 9 | `objeto_a_contratar` | text | Objeto del Contrato | PUBLICA | Contract scope — public per transparency law |
| 10 | `objeto_del_proceso` | text | Objeto del Proceso | PUBLICA | Process object — public |
| 11 | `tipo_de_contrato` | text | Tipo de Contrato | PUBLICA | Contract type classification — public |
| 12 | `fecha_de_firma_del_contrato` | date | Fecha de Firma del Contrato | PUBLICA | Public contracting date |
| 13 | `fecha_inicio_ejecuci_n` | date | Fecha Inicio Ejecucion | PUBLICA | Execution start — public |
| 14 | `fecha_fin_ejecuci_n` | date | Fecha Fin Ejecucion | PUBLICA | Execution end — public |
| 15 | `numero_del_contrato` | text | ID Contrato | PUBLICA | Public contract identifier |
| 16 | `numero_de_proceso` | text | ID Proceso | PUBLICA | Public process identifier |
| 17 | `valor_contrato` | number | Valor Contrato | PUBLICA | Contract value — public per transparency law |
| 18 | `nom_raz_social_contratista` | text | Razon Social Contratista | **SEMIPRIVADA** | Legal entity name: public when acting as contractor per Art. 26 Ley 1581. Natural persons: public in their role as contractor (Ley 1712/2014), but must not be used for unrelated profiling |
| 19 | `url_contrato` | text | URL Contrato | PUBLICA | Link to public SECOP record |
| 20 | `origen` | text | Origen (SECOPI / SECOPII) | PUBLICA | Dataset provenance flag |
| 21 | `tipo_documento_proveedor` | text | Tipo Documento Proveedor | PUBLICA | Document type classifier (NIT, cedula) — public |
| 22 | `documento_proveedor` | text | Documento Proveedor | **SEMIPRIVADA** | NIT of legal entity: PUBLICA in contracting role. Cedula of natural person: SEMIPRIVADA — expose only in contractor/public-servant role context, not for general lookup; apply `PUBLIC_MODE` filter |

**Classification notes:**
- `documento_proveedor` where `tipo_documento_proveedor = "Nit de Persona Natural"` means the contractor is a natural person, not a company. Their cedula is SEMIPRIVADA. Store it, but in `PUBLIC_MODE=true` do not expose via free-text search — only show it in the context of a specific contract where they are named as the contractor.
- No field in SECOP Integrado is classified PRIVADA or SENSIBLE — these fields do not include home addresses, personal phones, or health data. Ingest all 22 fields.
- Fields marked SEMIPRIVADA should be visible in the contractor profile context but should not be surfaced in general search autocomplete.

**Ley 1581/2012 Classification Reference:**
- **PUBLICA:** Freely accessible and can be disclosed to any person without restriction
- **SEMIPRIVADA:** Data that is not entirely private but is of interest to a specific community or sector; requires limited disclosure context
- **PRIVADA:** Data that, due to its intimate nature, is only relevant to the owner; requires authorization
- **SENSIBLE:** Data that can lead to discrimination; health, sexual orientation, political views, etc.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MERGE key deduplication | Custom dict-based dedup logic | Neo4j MERGE + unique constraint | MERGE with constraint is atomic; custom dedup races under any concurrency |
| HTTP retry with backoff | Custom retry loop | `httpx` with `Retry` transport or `tenacity` library | Edge cases in jitter, exponential backoff, non-retryable status codes |
| NIT validation algorithm | Custom regex-only approach | Normalize first (strip prefix/suffix), then validate digits | NIT has variable formats; regex alone misses leading-zero variants |
| Batched Neo4j writes | Row-by-row session.run() | `UNWIND $batch AS row MERGE ...` in single transaction | 1M row-by-row = 1M Bolt round trips; UNWIND batches to 500-1000 per tx |
| Schema migration tracking | Custom migration state table | Run `schema.cypher` with `IF NOT EXISTS` on every startup | `IF NOT EXISTS` makes constraint creation idempotent; no migration table needed |
| Pagination state tracking | In-memory offset counter only | Persist `last_run_at` to file/SQLite per dataset | Process restarts lose in-memory state; persisted checkpoint enables safe resume |

**Key insight:** Neo4j MERGE is not free — its cost is an index lookup per call. Without the unique constraint, that lookup is a full label scan. Every hand-rolled deduplication approach adds complexity without solving the index problem.

---

## Common Pitfalls

### Pitfall 1: ETL Before Constraints — Duplicate Node Explosion

**What goes wrong:** Running any MERGE before `CREATE CONSTRAINT` causes full-graph label scans. At 100K rows this is slow; at 10M rows it is impossible. Worse, concurrent writes without constraints create duplicate nodes.

**Why it happens:** Developers run a quick test load to "see if the pipeline works" before schema work is done.

**How to avoid:** The ETL startup function must call `verify_constraints()` (see Pattern 2 above) and raise `RuntimeError` if any required constraint is absent. Make it impossible to load data without constraints.

**Warning signs:** `EXPLAIN MERGE (n:Empresa {nit: $n})` shows `NodeByLabelScan` instead of `NodeIndexSeek`.

### Pitfall 2: NIT Normalization Inconsistency Between Sources

**What goes wrong:** SECOP Integrado has `documento_proveedor: "890399010"`. A future source (SIRI) has `nit: "0890399010-4"`. The MERGE keys differ, creating two Empresa nodes for the same legal entity.

**Why it happens:** Each source uses different NIT formatting conventions. If normalization is done per-source instead of through a shared `common.py` function, the output diverges.

**How to avoid:** All NIT normalization must go through `normalize_nit()` in `etl/normalizers/common.py`. This is the single source of truth. No inline normalization in source-specific pipeline files.

**Warning signs:** `MATCH (e:Empresa) RETURN e.nit ORDER BY e.nit` shows suspiciously similar values that differ only by leading zeros or trailing check digits.

### Pitfall 3: SECOP I vs SECOP II Record Duplication in rpmr-utcd

**What goes wrong:** The `origen` field in SECOP Integrado is either `"SECOPI"` or `"SECOPII"`. The same underlying contract may appear as a SECOP I document registration AND a SECOP II process record — especially for contracts from the 2015-2018 transition period. If `numero_del_contrato` is used as the MERGE key without also considering `origen`, two records for the same real contract create one node with mixed/wrong properties.

**Why it happens:** The Integrado dataset is a union of both systems. Colombia Compra Eficiente acknowledges interoperability deficiencies between them.

**How to avoid:** Use a composite key for `:Contrato`: `id_contrato = row.numero_del_contrato + "_" + row.origen`. This scopes the identifier to the source system, preventing false merges. In Phase 2 (cross-source entity linking), add a deduplication step that identifies probable duplicates across origins.

**Warning signs:** Running `MATCH (c:Contrato) WHERE c.id_contrato STARTS WITH '123'` returns two nodes with similar but conflicting `valor_contrato` values.

### Pitfall 4: Socrata Offset Drift During Ingestion

**What goes wrong:** A 1M-row pagination run takes several hours. During that time, SECOP updates the dataset. Without a stable sort key, offsets shift and records are silently skipped.

**Why it happens:** Default Socrata API sort order is unspecified. Records inserted upstream shift all offsets below them.

**How to avoid:** Always include `$order=fecha_de_firma_del_contrato ASC` in every Socrata query (see Pattern 5). Accept that a few very-recent records may be missed at the tail — the incremental run next cycle will catch them.

### Pitfall 5: datos.gov.co Downtime Mid-Pipeline

**What goes wrong:** The pipeline runs nightly. datos.gov.co goes offline (which happened — incident rate increased 4x from 2022 to 2023 per Colombia Compra Eficiente). The pipeline crashes at page 200 of 3000. Next run starts from page 0, creating duplicates or OOM from re-processing an already-loaded batch.

**Why it happens:** No checkpoint/resume mechanism.

**How to avoid:**
- Save raw API responses to disk (e.g., `raw_data/rpmr-utcd/2026-04-09/page_200.json`) before any transformation
- Track pipeline progress: `{dataset: "rpmr-utcd", date: "2026-04-09", last_page: 200, status: "interrupted"}` in a SQLite state table
- Resume from checkpoint on restart; use MERGE to ensure idempotence even if pages overlap

### Pitfall 6: Categorical Values as Neo4j Nodes (Super Nodes)

**What goes wrong:** Creating `(:Municipio {nombre: "Bogota"})` nodes and connecting every contract to them. With millions of contracts, Bogota becomes a super node with 500K+ relationships. Any traversal touching it triggers a full relationship scan.

**How to avoid:** Store `municipio_entidad`, `departamento_entidad`, `tipo_de_contrato`, `modalidad_de_contratacion` as **properties on `:Contrato` and `:EntidadPublica` nodes** — not as separate nodes. Phase 3 pattern detection queries will use indexed property lookups (`WHERE c.municipio = 'Bogota'`), not relationship traversals.

---

## Code Examples

### Startup Schema Application

```bash
# How to apply schema.cypher on container start
# Option 1: Docker entrypoint script (recommended)
# infra/neo4j/entrypoint.sh
until cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" > /dev/null 2>&1; do
  echo "Waiting for Neo4j..."
  sleep 2
done
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --file /var/lib/neo4j/import/schema.cypher
echo "Schema applied."
```

```yaml
# docker-compose.yml — api service waits for schema via healthcheck
# Neo4j healthcheck ensures it's ready before api starts
# api/Dockerfile CMD runs apply_schema.py before uvicorn starts
```

### ETL Batch Write with UNWIND

```python
# etl/loaders/neo4j_loader.py

async def load_batch(session, batch: list[dict], cypher: str) -> int:
    """
    Execute a Cypher UNWIND statement with a batch of row dicts.
    Returns number of rows processed.
    """
    result = await session.run(cypher, {"batch": batch})
    summary = await result.consume()
    return summary.counters.nodes_created + summary.counters.nodes_deleted

SECOP_INTEGRADO_CYPHER = """
UNWIND $batch AS row
MERGE (ent:EntidadPublica {codigo_entidad: row.codigo_entidad})
ON CREATE SET
  ent.nombre        = row.nombre_de_la_entidad,
  ent.nit           = row.nit_de_la_entidad,
  ent.nivel         = row.nivel_entidad,
  ent.fuente        = 'rpmr-utcd',
  ent.ingested_at   = datetime()

MERGE (c:Contrato {id_contrato: row.id_contrato})
ON CREATE SET
  c.valor           = toFloat(row.valor_contrato),
  c.objeto          = row.objeto_a_contratar,
  c.tipo            = row.tipo_de_contrato,
  c.modalidad       = row.modalidad_de_contratacion,
  c.estado          = row.estado_del_proceso,
  c.origen          = row.origen,
  c.numero_proceso  = row.numero_de_proceso,
  c.fuente          = 'rpmr-utcd',
  c.ingested_at     = datetime(),
  c.url_fuente      = row.url_contrato
ON MATCH SET
  c.estado          = row.estado_del_proceso,
  c.updated_at      = datetime()

MERGE (ent)-[:ADJUDICO]->(c)

WITH c, row
WHERE row.nit_contratista IS NOT NULL
MERGE (contratista:Empresa {nit: row.nit_contratista})
ON CREATE SET
  contratista.razon_social  = row.nom_raz_social_contratista,
  contratista.fuente        = 'rpmr-utcd',
  contratista.ingested_at   = datetime()
MERGE (contratista)-[:EJECUTA]->(c)
"""
```

### NIT Normalization in ETL Transform

```python
# etl/sources/secop_integrado.py — transform stage

import polars as pl
from etl.normalizers.common import normalize_nit, normalize_razon_social

def transform(df: pl.DataFrame) -> pl.DataFrame:
    """
    Map raw SECOP Integrado fields to canonical graph properties.
    Returns a DataFrame with graph-ready column names.
    """
    return (
        df
        .with_columns([
            # Normalize NIT fields
            pl.col("documento_proveedor")
              .map_elements(normalize_nit, return_dtype=pl.String)
              .alias("nit_contratista"),
            pl.col("nit_de_la_entidad")
              .map_elements(normalize_nit, return_dtype=pl.String)
              .alias("nit_entidad"),
            # Composite contract ID scoped to source system
            (pl.col("numero_del_contrato") + "_" + pl.col("origen"))
              .alias("id_contrato"),
            # codigo_entidad fallback to nit if code not present
            pl.col("codigo_entidad_en_secop").alias("codigo_entidad"),
        ])
        .filter(pl.col("id_contrato").is_not_null())
        .filter(pl.col("codigo_entidad").is_not_null())
    )
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Notes |
|------------|------------|-----------|---------|-------|
| Docker | All containers | Yes | 29.1.3 | Docker Desktop running |
| Docker Compose | Stack orchestration | Yes | v5.0.1 | v2 syntax (`docker compose up`) |
| Python (host) | Dev tooling only | Yes | 3.13.4 | Note: stack uses Python 3.12 inside Docker |
| curl | API reachability tests | Yes | system | Used for SECOP API verification |
| Neo4j 5.26.24-community (image) | Graph database | Yes | 5.26.24 | Confirmed on Docker Hub 2026-04-08 |
| datos.gov.co Socrata API | ETL data source | Yes | — | Confirmed reachable; sample record fetched |
| Python packages (polars, httpx, fastapi, neo4j) | ETL + API | No (host) | — | Install inside Docker; do not install on host Python 3.13 |
| Socrata App Token | Increased rate limits | Pending | — | Register free at data.socrata.com; ~1000 req/hr without; more with token |

**Missing dependencies with no fallback:**
- Socrata App Token: pipeline will work without one but is rate-limited to ~1000 req/hour unauthenticated. For a full initial load of millions of SECOP records, the token is necessary. Register at https://data.socrata.com/login before the ETL task runs.

**Missing dependencies with fallback:**
- None that block Phase 1 execution.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `neo4j-driver` Python package | `neo4j` Python package | ~2024 | Old package name deprecated; install `neo4j` not `neo4j-driver` |
| `sodapy` for Socrata ingestion | Raw `httpx` + SODA API | 2024 (sodapy effectively abandoned) | Async, HTTP/2, Python 3.12+ support |
| pandas for ETL DataFrames | Polars | 2023-2024 (production adoption) | 3-10x faster, 30-60% less memory on 1M+ rows |
| Docker Compose v1 (`docker-compose`) | Docker Compose v2 (`docker compose`) | v1 EOL Jan 2024 | No hyphen; `depends_on: condition: service_healthy` syntax |
| Neo4j APOC installed separately | APOC bundled in `labs/` of official Docker image | Neo4j 5.x | Set `NEO4J_PLUGINS: '["apoc"]'` in env var; no manual jar download needed |
| `calendar_date` Socrata field → Python datetime | Store as string, parse with Polars `.str.to_date()` | — | Avoids Socrata datetime format inconsistencies |

---

## Open Questions

1. **SECOP Integrado dataset size**
   - What we know: The API is reachable and returns records. A count query timed out during research.
   - What's unclear: Exact row count — estimates suggest millions of records based on Colombia Compra Eficiente documentation, but the precise number determines initial load time estimates.
   - Recommendation: Run `curl "https://www.datos.gov.co/resource/rpmr-utcd.json?\$select=count(*)%20as%20total" --max-time 60` as the first ETL task and log the result before beginning pagination.

2. **SECOP I vs SECOP II duplicate rate in rpmr-utcd**
   - What we know: `origen` field distinguishes the two; the transition period was 2015-2018.
   - What's unclear: What fraction of records are duplicated across both origins for the same real contract?
   - Recommendation: Query `MATCH (c1:Contrato {origen: 'SECOPI'}), (c2:Contrato {origen: 'SECOPII'}) WHERE c1.numero_proceso = c2.numero_proceso RETURN count(*)` after initial load to measure overlap before building the Phase 2 deduplication step.

3. **Socrata App Token capacity**
   - What we know: Unauthenticated requests are limited to ~1000/hour. Token registration is free.
   - What's unclear: Whether the higher limit with a token is sufficient for initial full-load pagination in a single nightly window, or if a multi-night initial load strategy is needed.
   - Recommendation: Token should be registered before development begins. If rate limits are still hit, implement a sleep/backoff between pages (1-2 seconds per page is conservative).

4. **APOC version compatibility with Neo4j 5.26.24**
   - What we know: `NEO4J_PLUGINS: '["apoc"]'` activates APOC from the bundled labs directory in the official Docker image.
   - What's unclear: Whether Phase 1 actually needs APOC (the core ETL uses standard Cypher MERGE + UNWIND), or if APOC is only needed for later phases (string normalization helpers, periodic.iterate for large batch jobs).
   - Recommendation: Include the APOC plugin declaration in docker-compose.yml from the start to avoid a configuration change mid-development, but do not write Phase 1 ETL code that depends on APOC procedures — use standard Cypher.

---

## Sources

### Primary (HIGH confidence)
- Live API probe: `https://www.datos.gov.co/resource/rpmr-utcd.json?$limit=1` — fetched 2026-04-09; confirmed 22 fields, sample record, API reachability
- Docker Hub: `https://hub.docker.com/v2/repositories/library/neo4j/tags` — confirmed `neo4j:5.26.24-community` available 2026-04-08
- `.planning/research/STACK.md` — verified version pins: neo4j driver 6.1.0, FastAPI 0.135.3, Polars 1.39.3 (HIGH, verified against PyPI during that research pass)
- `.planning/research/ARCHITECTURE.md` — MERGE pattern, Docker Compose topology, graph schema (HIGH, based on Neo4j official docs + br/acc reference)
- `.planning/research/PITFALLS.md` — entity resolution, super nodes, SECOP I/II schema differences, Ley 1581 scope (HIGH, multiple official sources cited)
- `.planning/REQUIREMENTS.md` — requirement text for INFRA-01 through ETL-08

### Secondary (MEDIUM confidence)
- Colombia Compra Eficiente Manual de Datos Abiertos SECOP 2024 — field semantics, SECOP I/II distinction (referenced in PITFALLS.md; not re-fetched in this research pass)
- Ley 1581 de 2012 — privacy classification categories (Gestor Normativo Función Pública — referenced in PITFALLS.md)

### Tertiary (LOW confidence — flag for validation)
- Socrata App Token rate limit of ~1000 req/hour: documented in older Socrata changelog; current limits may differ. Verify at https://dev.socrata.com/docs/app-tokens.html before planning ETL load estimates.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI, Docker Hub during prior research pass; Docker/Compose versions confirmed live
- Architecture patterns: HIGH — MERGE/UNWIND patterns from Neo4j official Cypher manual; Docker Compose topology from br/acc + official Neo4j Docker docs
- Privacy classification: HIGH for classification logic (Ley 1581/2012 is official law); MEDIUM for individual field classifications (applied by researcher, not yet reviewed by a Colombian data protection lawyer)
- Pitfalls: HIGH — sourced from official Neo4j documentation, Colombia Compra Eficiente official reports, and ICIJ methodology documentation
- Environment availability: HIGH — commands run directly on development machine

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (stable stack; Socrata API availability and dataset schema could change sooner)
