# Phase 3: Backend API — Context

**Phase:** 03-backend-api
**Captured:** 2026-04-09
**Depends on:** Phase 2 (Full ETL) — all Socrata sources loaded, entity linking complete
**Requirements:** API-01, API-02, API-03, API-04, API-05, API-06, API-07, PRIV-02, PRIV-03

---

## What Phase 3 Delivers

FastAPI exposes the graph as a REST API investigators can query. Four endpoint groups: search, contractor profile, contract detail, and graph traversal. A privacy middleware gate enforces Ley 1581/2012 when `PUBLIC_MODE=true`. Every response carries provenance and freshness metadata.

---

## Decisions

### Router Structure

Four new routers added to `api/routers/`:

| Router | Endpoint | Requirement |
|--------|----------|-------------|
| `search.py` | `GET /api/v1/search` | API-01 |
| `contractors.py` | `GET /api/v1/contractor/{id}` | API-02 |
| `contracts.py` | `GET /api/v1/contract/{id}` | API-03 |
| `graph.py` | `GET /api/v1/graph/{id}` | API-04 |

All routers prefixed `/api/v1` in `main.py`. Router handlers call service functions. No Cypher in handlers.

**Rationale:** Follows the existing pattern from `api/routers/health.py`. Keeps Cypher isolated in `api/services/` for testability. Four routers map cleanly to the four requirement groups.

### Search: Fuzzy Matching via Neo4j Fulltext Indexes

Fulltext indexes (`FULLTEXT INDEX`) on `Empresa.razon_social`, `Persona.nombre`, and `EntidadPublica.nombre` enable fuzzy/substring search in Cypher using `db.index.fulltext.queryNodes()`. This handles common Colombian typos (accent variations, apostrophes, abbreviations) without a separate search engine.

```cypher
CALL db.index.fulltext.queryNodes('entity_search_idx', $q)
YIELD node, score
RETURN node, score ORDER BY score DESC LIMIT 20
```

Index creation goes into `infra/neo4j/schema.cypher` as `CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS FOR (n:Empresa|Persona|EntidadPublica) ON EACH [n.razon_social, n.nombre]`.

**Rationale:** Native Neo4j fulltext avoids adding Elasticsearch/OpenSearch to the stack. Sufficient for name search across <10M nodes. Lucene-based — handles diacritics and fuzzy operators natively.

**Alternative rejected:** Levenshtein in Python after a CONTAINS query — too slow on large datasets, misses phonetic variants.

### Privacy Middleware: PUBLIC_MODE

A FastAPI middleware (`api/middleware/privacy.py`) reads `settings.public_mode` (already in `config.py` as `public_mode: bool = True`). In public mode it strips fields tagged as protected from response bodies before sending.

Protected fields (Ley 1581/2012):
- `email`, `telefono_personal`, `direccion_residencia` on `Persona` nodes
- Any field classified `PRIVADA` or `SENSIBLE` in the Phase 1 privacy inventory

Implementation: response middleware intercepts JSON bodies and applies a field allowlist per node label. Uses a `PrivacyFilter` class with a `filter_node(label, props) -> props` method called from service functions (not as HTTP middleware to avoid full JSON re-parse on every response).

**Decision:** Privacy filtering runs in service functions, not HTTP middleware. Service functions know the label of each node they return; HTTP middleware would need to re-parse and introspect the response body blindly.

**Rationale:** Aligns with ARCHITECTURE.md Anti-Pattern 5. `PUBLIC_MODE` is already in `config.py` from Phase 1. Adding a `PrivacyFilter` class keeps the logic testable in isolation.

### Graph Traversal: Depth Capped at 2, Timeout 30s

`GET /api/v1/graph/{id}?depth=2` (default 2, max 2, not configurable in public API).

Cypher pattern:
```cypher
MATCH (root {id: $id})-[r*..2]-(neighbor)
RETURN root, r, neighbor LIMIT 500
```

Query timeout enforced via Neo4j driver transaction timeout:
```python
session.run(query, timeout=30)  # 30-second hard limit
```

Results capped at 500 nodes/edges total. If the traversal exceeds 500 results, the response includes `truncated: true`.

**Rationale:** ARCHITECTURE.md documents unbounded traversal as Anti-Pattern 2. Phase 3 success criteria explicitly require depth=2 and 30s timeout. Colombian contractor networks can be dense (large entidades with hundreds of contracts); without a cap, common queries would OOM.

### Provenance and Freshness in Every Response

Every response envelope includes:
```json
{
  "data": { ... },
  "meta": {
    "fuentes": [
      { "dataset_id": "rpmr-utcd", "nombre": "SECOP Integrado", "last_ingested": "2026-04-09T03:00:00Z" },
      { "dataset_id": "jbjy-vk9h", "nombre": "SECOP II Contratos", "last_ingested": "2026-04-08T03:00:00Z" }
    ],
    "generated_at": "2026-04-09T12:34:56Z"
  }
}
```

Freshness is queried from a `SourceIngestion` node (or property on a `__meta__` node) that ETL pipelines update on each run with `last_ingested_at`. If no ingestion record exists for a source, `last_ingested` is `null`.

**Requirement:** API-07 and PRIV-03 both require provenance visible in API responses.

### Rate Limiting

`slowapi` (wraps `limits` library, integrates with FastAPI) provides per-IP rate limiting without Redis. Default limit: 60 requests/minute per IP, applied to all `/api/v1/` routes via a `@limiter.limit("60/minute")` decorator on each router.

**Rationale:** Protects Neo4j from runaway clients. `slowapi` is the idiomatic FastAPI rate limiter — no broker required, in-process, sufficient for MVP traffic. Added to `api/requirements.txt`.

**Alternative rejected:** nginx-level rate limiting — would require nginx config changes and doesn't give per-endpoint granularity.

### New File Structure

```
api/
├── main.py                    (updated: register new routers, slowapi limiter)
├── config.py                  (unchanged)
├── dependencies.py            (unchanged)
├── middleware/
│   └── privacy.py             (NEW: PrivacyFilter class)
├── routers/
│   ├── health.py              (unchanged)
│   ├── search.py              (NEW)
│   ├── contractors.py         (NEW)
│   ├── contracts.py           (NEW)
│   └── graph.py               (NEW)
├── services/
│   ├── search_service.py      (NEW: Cypher for fulltext search)
│   ├── contractor_service.py  (NEW: Cypher for profile aggregation)
│   ├── contract_service.py    (NEW: Cypher for contract detail)
│   ├── graph_service.py       (NEW: Cypher for traversal)
│   └── freshness_service.py   (NEW: query last_ingested_at per source)
└── models/
    ├── entities.py            (NEW: Pydantic models for Empresa, Persona, etc.)
    ├── graph.py               (NEW: GraphResponse, NodeDTO, EdgeDTO)
    └── responses.py           (NEW: envelope with meta/fuentes)
```

`infra/neo4j/schema.cypher` gets two additions:
- `CREATE FULLTEXT INDEX entity_search_idx` for fuzzy search
- `SourceIngestion` node pattern documentation (created by ETL, read by freshness_service)

---

## Constraints Inherited from Earlier Phases

| Constraint | Source |
|------------|--------|
| `public_mode: bool = True` already in `config.py` | Phase 1 |
| Neo4j async driver via `lifespan` in `main.py` | Phase 1 |
| `get_neo4j_session` dependency injector in `dependencies.py` | Phase 1 |
| All ETL sources tagged with `fuente` provenance on every node | Phase 1 + 2 |
| No Cypher in route handlers | ARCHITECTURE.md |
| Separate MERGE per node before relationship MERGE | ARCHITECTURE.md Anti-Pattern 1 |

---

## What is NOT in Phase 3

| Deferred | Phase |
|----------|-------|
| Pattern detection endpoints (PAT-01 through PAT-05) | Phase 4 |
| Frontend UI | Phase 4 |
| RBAC / user accounts | Out of scope |
| Cypher passthrough endpoint (ADV-01) | v2 |
| CSV/JSON export (ADV-03) | v2 |

---

## User Preference

User selected YOLO mode. All implementation decisions within the above constraints are at Claude's discretion. No user confirmation required before writing code.
