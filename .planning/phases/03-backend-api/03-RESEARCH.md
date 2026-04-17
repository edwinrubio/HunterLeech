# Phase 3: Backend API — Research

**Phase:** 03-backend-api
**Researched:** 2026-04-09
**Domain:** FastAPI routers, Neo4j fulltext indexes, Cypher profile queries, graph traversal, rate limiting, privacy middleware
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | Endpoint de busqueda por NIT, cedula o nombre con fuzzy matching | Neo4j fulltext index + `db.index.fulltext.queryNodes()` — native Lucene fuzzy search without external engine |
| API-02 | Endpoint de perfil de contratista: contratos, sanciones, entidades relacionadas | Cypher aggregation query returning Empresa + EJECUTA contracts + SANCIONO sanctions in one call |
| API-03 | Endpoint de detalle de contrato: valor, entidad, modalidad, plazo, oferentes | Cypher match on `id_contrato` returning Contrato + ADJUDICO entidad + PARTICIPO oferentes |
| API-04 | Endpoint de grafo de relaciones: nodos y aristas para un entity dado con profundidad configurable | Variable-length path `[*..2]` capped at depth 2 + LIMIT 500; 30s driver timeout |
| API-05 | Middleware de privacidad (PUBLIC_MODE): oculta campos sensibles segun Ley 1581/2012 | `PrivacyFilter` class in service layer; `settings.public_mode` already in config.py |
| API-06 | Rate limiting y timeout en queries para proteger Neo4j | `slowapi` for per-IP rate limits; Neo4j driver `timeout` param for Cypher timeout |
| API-07 | Indicador de frescura de datos por fuente en respuestas API | `SourceIngestion` nodes written by ETL; `freshness_service.py` queries `last_ingested_at` per source |
| PRIV-02 | PUBLIC_MODE desactiva exposicion de datos personales protegidos por Ley 1581/2012 | Field allowlist per node label; strips email, telefono_personal, direccion_residencia |
| PRIV-03 | Toda relacion mostrada incluye fuente y significado semantico (no implicar culpabilidad) | `fuente` property on every relationship returned in API responses; semantic labels in response models |
</phase_requirements>

---

## Summary

Phase 3 adds four routers and their backing services on top of the existing FastAPI skeleton from Phase 1. The heaviest technical work is: (1) creating the fulltext index in Neo4j for fuzzy search, (2) writing the Cypher queries for contractor profile aggregation, and (3) wiring the privacy filter into service functions.

The existing codebase gives us clean patterns to extend:
- `api/config.py` already has `public_mode: bool = True`
- `api/dependencies.py` already has `get_neo4j_session` for dependency injection
- `api/routers/health.py` is the router pattern to follow
- `etl/loaders/neo4j_loader.py` shows the async driver session pattern
- `infra/neo4j/schema.cypher` already has `CREATE INDEX` statements — fulltext index goes here

No new infrastructure services needed. `slowapi` is an in-process rate limiter that requires no Redis. Privacy filter is a Python class, not a separate service.

---

## Standard Stack (Phase 3 Additions)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| slowapi | 0.1.9 | Per-IP rate limiting in FastAPI | In-process, no broker, idiomatic FastAPI integration via `Limiter` class |
| limits | (slowapi dep) | Rate limit backend | In-memory store sufficient for single-node MVP deployment |

No new Docker services. No new databases. `slowapi` goes into `api/requirements.txt`.

---

## Finding 1: Neo4j Fulltext Index Setup

### Index Definition

Fulltext indexes in Neo4j 5.x support multi-label, multi-property configurations. The correct Cypher:

```cypher
CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS
FOR (n:Empresa|Persona|EntidadPublica)
ON EACH [n.razon_social, n.nombre];
```

This creates a single Lucene index covering all three node labels on the name fields. The `IF NOT EXISTS` makes it idempotent — safe to re-run from `schema.cypher`.

### Query Pattern

```cypher
CALL db.index.fulltext.queryNodes('entity_search_idx', $q)
YIELD node, score
RETURN
  labels(node)[0] AS tipo,
  node.nit AS nit,
  node.cedula AS cedula,
  node.razon_social AS nombre,
  node.nombre AS nombre_persona,
  score
ORDER BY score DESC
LIMIT 20
```

For NIT/cedula exact lookup (when query looks like a number):
```cypher
MATCH (n)
WHERE n.nit = $q OR n.cedula = $q
RETURN labels(n)[0] AS tipo, n
LIMIT 5
```

The search router detects if `q` is numeric (after stripping hyphens/dots) and routes to exact lookup; otherwise uses fulltext.

### Lucene Fuzzy Operators

The Lucene query language (used by Neo4j fulltext) supports:
- `q~` — fuzzy match (Damerau-Levenshtein distance 1 by default)
- `q~0.8` — explicit similarity threshold
- `q*` — prefix match

The service appends `~` to the user query for fuzzy matching: `f"{q}~"` unless the query is a NIT/cedula.

### Scoring

`score` from `db.index.fulltext.queryNodes` is a Lucene relevance score (TF-IDF based). Useful for ordering results — no need to implement our own ranking.

---

## Finding 2: FastAPI Middleware Pattern for PUBLIC_MODE

### Chosen Approach: Service-Layer Filter (Not HTTP Middleware)

HTTP middleware in FastAPI operates on raw request/response bytes. For privacy filtering we need to know the Neo4j node label to apply the correct field allowlist — that context is available in service functions, not at the HTTP layer.

### PrivacyFilter Class

```python
# api/middleware/privacy.py

from api.config import settings

# Fields stripped when PUBLIC_MODE=true, keyed by node label
PROTECTED_FIELDS: dict[str, set[str]] = {
    "Persona": {"email", "telefono_personal", "direccion_residencia", "fecha_nacimiento"},
    "Empresa": set(),  # no protected fields for legal entities
    "EntidadPublica": set(),
    "Contrato": set(),
    "Sancion": set(),
}


class PrivacyFilter:
    def __init__(self, public_mode: bool):
        self.public_mode = public_mode

    def filter_node(self, label: str, props: dict) -> dict:
        """Remove protected fields from a node's properties dict."""
        if not self.public_mode:
            return props
        blocked = PROTECTED_FIELDS.get(label, set())
        return {k: v for k, v in props.items() if k not in blocked}

    def filter_graph_nodes(self, nodes: list[dict]) -> list[dict]:
        """Apply filter_node to each node in a graph response."""
        return [
            {**n, "properties": self.filter_node(n["label"], n["properties"])}
            for n in nodes
        ]
```

### Dependency Injection

```python
# api/dependencies.py (addition)
from functools import lru_cache
from api.middleware.privacy import PrivacyFilter
from api.config import settings

@lru_cache
def get_privacy_filter() -> PrivacyFilter:
    return PrivacyFilter(public_mode=settings.public_mode)
```

Service functions receive `PrivacyFilter` via `Depends(get_privacy_filter)`.

---

## Finding 3: Cypher Queries for Contractor Profile

### Empresa Profile (NIT-based)

```cypher
MATCH (e:Empresa {nit: $nit})
OPTIONAL MATCH (e)-[:EJECUTA]->(c:Contrato)
OPTIONAL MATCH (entidad:EntidadPublica)-[:ADJUDICO]->(c)
OPTIONAL MATCH (e)-[:SANCIONO]->(s:Sancion)
OPTIONAL MATCH (p:Persona)-[:REPRESENTA]->(e)
RETURN
  e AS empresa,
  collect(DISTINCT {
    id_contrato: c.id_contrato,
    objeto: c.objeto,
    valor: c.valor,
    fecha_inicio: c.fecha_inicio,
    fecha_fin: c.fecha_fin,
    modalidad: c.modalidad,
    entidad: entidad.nombre,
    fuente: c.fuente
  }) AS contratos,
  collect(DISTINCT {
    id_sancion: s.id_sancion,
    tipo: s.tipo,
    fecha: s.fecha,
    autoridad: s.autoridad,
    descripcion: s.descripcion,
    fuente: s.fuente
  }) AS sanciones,
  collect(DISTINCT {
    nombre: p.nombre,
    cargo: p.cargo,
    cedula: p.cedula
  }) AS representantes
```

### Handling Large Result Sets

If a contractor has >1,000 contracts (common for large construction companies), the OPTIONAL MATCH collect would be slow. Add `LIMIT 100` on the contract subquery using a subquery clause (Neo4j 5.x supports `CALL { ... } IN TRANSACTIONS`):

```cypher
MATCH (e:Empresa {nit: $nit})
CALL {
  WITH e
  MATCH (e)-[:EJECUTA]->(c:Contrato)
  OPTIONAL MATCH (entidad:EntidadPublica)-[:ADJUDICO]->(c)
  RETURN c, entidad ORDER BY c.fecha_inicio DESC LIMIT 100
}
...
```

The profile response includes `contratos_total` (count without LIMIT) alongside the paginated `contratos` list.

### Persona Profile (cedula-based)

```cypher
MATCH (p:Persona {cedula: $cedula})
OPTIONAL MATCH (p)-[:REPRESENTA]->(e:Empresa)
OPTIONAL MATCH (entidad:EntidadPublica)-[:EMPLEA]->(p)
OPTIONAL MATCH (p)-[:SANCIONO]->(s:Sancion)
RETURN p AS persona,
  collect(DISTINCT e) AS empresas_representadas,
  collect(DISTINCT entidad) AS empleadores,
  collect(DISTINCT s) AS sanciones
```

In PUBLIC_MODE, the `persona` node properties are filtered by `PrivacyFilter` before returning.

---

## Finding 4: Graph Traversal Queries with Depth Limit

### Core Pattern

```cypher
MATCH (root)
WHERE root.nit = $id OR root.cedula = $id OR root.id_contrato = $id OR root.codigo_entidad = $id
CALL {
  WITH root
  MATCH path = (root)-[r*..2]-(neighbor)
  RETURN nodes(path) AS path_nodes, relationships(path) AS path_rels
  LIMIT 500
}
WITH collect(DISTINCT path_nodes) AS all_node_lists,
     collect(DISTINCT path_rels) AS all_rel_lists
UNWIND all_node_lists AS node_list
UNWIND node_list AS n
WITH collect(DISTINCT n) AS nodes, all_rel_lists
UNWIND all_rel_lists AS rel_list
UNWIND rel_list AS r
RETURN nodes, collect(DISTINCT r) AS rels
```

In practice, `LIMIT 500` applies to the number of paths, not nodes/edges — which can explode. A safer implementation: use `apocPath.expand()` from APOC Core if available, or manually bound with:

```cypher
MATCH (root)
WHERE root.nit = $id OR root.cedula = $id
WITH root
MATCH (root)-[r1]-(n1)
OPTIONAL MATCH (n1)-[r2]-(n2)
  WHERE n2 <> root
RETURN root, collect(DISTINCT {rel: r1, node: n1}) AS layer1,
             collect(DISTINCT {rel: r2, node: n2}) AS layer2
LIMIT 500
```

This two-layer expansion is deterministic and avoids the combinatorial explosion of `[*..2]` on dense nodes.

### Driver Timeout

```python
async with session.begin_transaction(timeout=30.0) as tx:
    result = await tx.run(query, id=entity_id)
    records = await result.data()
```

If the query exceeds 30 seconds, Neo4j raises `ClientError` with code `Neo.ClientError.Transaction.TransactionTimedOut`. The router catches this and returns HTTP 408.

### Response Serialization

```python
class NodeDTO(BaseModel):
    id: str
    label: str
    properties: dict

class EdgeDTO(BaseModel):
    source: str
    target: str
    type: str
    properties: dict

class GraphResponse(BaseModel):
    nodes: list[NodeDTO]
    edges: list[EdgeDTO]
    truncated: bool
    meta: ResponseMeta
```

---

## Finding 5: Rate Limiting with slowapi

### Installation

```
slowapi==0.1.9
```

Add to `api/requirements.txt`.

### Integration Pattern

```python
# api/main.py additions
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

```python
# In each router
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.get("/search")
@limiter.limit("60/minute")
async def search(request: Request, q: str, session=Depends(get_neo4j_session)):
    ...
```

`_rate_limit_exceeded_handler` returns HTTP 429 with a `Retry-After` header.

### Limits Applied

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| `GET /api/v1/search` | 60/minute | Text search is cheap; higher limit acceptable |
| `GET /api/v1/contractor/{id}` | 30/minute | Aggregation query is heavier |
| `GET /api/v1/contract/{id}` | 60/minute | Simple node lookup |
| `GET /api/v1/graph/{id}` | 10/minute | Traversal query is most expensive |

---

## Finding 6: Freshness Service

### How ETL Pipelines Record Ingestion

Each ETL pipeline upserts a `SourceIngestion` node at pipeline completion:

```cypher
MERGE (si:SourceIngestion {dataset_id: $dataset_id})
SET si.last_ingested_at = datetime(),
    si.record_count = $record_count,
    si.dataset_nombre = $nombre
```

This is written by each pipeline in its `load()` method after successful batch writes.

### Freshness Query

```cypher
MATCH (si:SourceIngestion)
RETURN si.dataset_id AS dataset_id,
       si.dataset_nombre AS nombre,
       si.last_ingested_at AS last_ingested_at,
       si.record_count AS record_count
ORDER BY si.dataset_id
```

The freshness service runs this once per API request (or cached with a 5-minute TTL using a module-level dict keyed by dataset_id).

### Response Envelope

Every response is wrapped:

```python
class FuenteMeta(BaseModel):
    dataset_id: str
    nombre: str
    last_ingested_at: datetime | None

class ResponseMeta(BaseModel):
    fuentes: list[FuenteMeta]
    generated_at: datetime

class APIResponse(BaseModel, Generic[T]):
    data: T
    meta: ResponseMeta
```

---

## Finding 7: Existing Code Patterns to Follow

### Router Pattern (from `api/routers/health.py`)

```python
from fastapi import APIRouter, Depends
from neo4j import AsyncSession
from dependencies import get_neo4j_session

router = APIRouter()

@router.get("/endpoint")
async def handler(session: AsyncSession = Depends(get_neo4j_session)):
    ...
```

All new routers follow this exact pattern. Router is imported and registered in `main.py` with `app.include_router(router, prefix="/api/v1")`.

### Neo4j Session (from `api/dependencies.py`)

```python
async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]:
    async with driver.session(database="neo4j") as session:
        yield session
```

No changes needed. New services receive session via `Depends(get_neo4j_session)`.

### Config (from `api/config.py`)

`settings.public_mode` already exists as `bool = True`. No changes to config.py.

---

## Finding 8: Files to Create / Modify

### New Files

| File | Purpose |
|------|---------|
| `api/middleware/__init__.py` | Package |
| `api/middleware/privacy.py` | PrivacyFilter class |
| `api/models/__init__.py` | Package |
| `api/models/entities.py` | Pydantic models: Empresa, Persona, Contrato, Sancion DTOs |
| `api/models/graph.py` | NodeDTO, EdgeDTO, GraphResponse |
| `api/models/responses.py` | APIResponse envelope, ResponseMeta, FuenteMeta |
| `api/services/__init__.py` | Package |
| `api/services/search_service.py` | Fulltext search Cypher |
| `api/services/contractor_service.py` | Profile aggregation Cypher |
| `api/services/contract_service.py` | Contract detail Cypher |
| `api/services/graph_service.py` | Traversal Cypher |
| `api/services/freshness_service.py` | SourceIngestion query + TTL cache |
| `api/routers/search.py` | GET /api/v1/search |
| `api/routers/contractors.py` | GET /api/v1/contractor/{id} |
| `api/routers/contracts.py` | GET /api/v1/contract/{id} |
| `api/routers/graph.py` | GET /api/v1/graph/{id} |

### Modified Files

| File | Change |
|------|--------|
| `api/main.py` | Add slowapi limiter, register 4 new routers |
| `api/requirements.txt` | Add `slowapi==0.1.9` |
| `api/dependencies.py` | Add `get_privacy_filter()` dependency |
| `infra/neo4j/schema.cypher` | Add fulltext index + SourceIngestion index |

---

## Risk: SourceIngestion Nodes Don't Exist Yet

Phase 2 ETL pipelines (02-02-PLAN.md) are not yet complete. The freshness service must gracefully handle the case where `SourceIngestion` nodes haven't been written yet. `freshness_service.py` returns `last_ingested_at: null` when no matching node exists — the response envelope is still valid, just shows null freshness.

This is safe: API-07 says "show freshness indicator"; null is a valid indicator meaning "never ingested".

The ETL pipelines in Phase 2 will need to be updated to write `SourceIngestion` nodes. This is documented as a dependency note in the plans.

---

## Sources

- [Neo4j Fulltext Index Cypher Manual](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/full-text-indexes/) — fulltext index creation and query syntax
- [Neo4j Python Driver Async Transactions](https://neo4j.com/docs/api/python-driver/current/async_api.html) — timeout parameter in begin_transaction
- [slowapi PyPI](https://pypi.org/project/slowapi/) — version 0.1.9 confirmed
- [slowapi GitHub](https://github.com/laurentS/slowapi) — FastAPI integration pattern
- `api/config.py` — `public_mode: bool = True` already defined
- `api/routers/health.py` — router pattern established in Phase 1
- `api/dependencies.py` — session injection pattern established in Phase 1
- `etl/loaders/neo4j_loader.py` — async driver session pattern
- `infra/neo4j/schema.cypher` — existing index definitions (Phase 1)
- `.planning/research/ARCHITECTURE.md` — Anti-Pattern 2 (unbounded traversal), Anti-Pattern 5 (privacy gate)
- `.planning/REQUIREMENTS.md` — API-01 through API-07, PRIV-02, PRIV-03
