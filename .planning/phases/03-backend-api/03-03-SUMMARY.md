---
phase: 03-backend-api
plan: "03"
subsystem: api
tags: [graph-traversal, neo4j-subgraph, privacy, rate-limiting, depth-2-expansion, timeout]
dependency_graph:
  requires:
    - 03-01 (PrivacyFilter, APIResponse envelope, freshness_service, get_neo4j_session, get_privacy_filter)
    - 03-02 (router pattern, limiter pattern, freshness integration pattern)
  provides:
    - GET /api/v1/graph/{id} — depth-2 subgraph centered on any entity
    - graph_service.get_subgraph() — two-layer Cypher expansion with 30s timeout
    - NodeDTO, EdgeDTO, GraphResponse Pydantic models (Sigma.js/graphology target format)
  affects:
    - api/main.py (graph_router added; now registers all 5 Phase 3 routes)
tech_stack:
  added: []
  patterns:
    - Explicit two-layer expansion (layer1 + layer2) instead of [*..2] to avoid combinatorial explosion
    - begin_transaction(timeout=30.0) for hard query timeout enforcement
    - _label field on every edge property dict for Spanish semantic labeling (PRIV-03)
    - privacy.filter_node() applied per-node in service layer (consistent with 03-01 pattern)
    - TimeoutError raised from service; caught in router as HTTP 408
key_files:
  created:
    - api/models/graph.py
    - api/services/graph_service.py
    - api/routers/graph.py
  modified:
    - api/main.py
decisions:
  - "Two-layer expansion (explicit layer1 + layer2 queries) chosen over [*..2] — avoids combinatorial path explosion on dense contractor networks (Anti-Pattern 2 from ARCHITECTURE.md)"
  - "MAX_NODES=300 and MAX_EDGES=500 chosen as conservative caps: enough for a readable force-directed graph in Sigma.js without browser memory pressure"
  - "TimeoutError raised from service layer, not swallowed — router catches and converts to HTTP 408 to give client actionable feedback"
  - "Layer-2 expansion excludes root node via NOT clause to prevent trivial back-edges inflating edge count"
  - "_label added to every edge properties dict (not a top-level field) for PRIV-03 compliance — avoids bare relationship type codes in API responses"
metrics:
  duration: "~3 minutes"
  completed_date: "2026-04-09"
  tasks_completed: 3
  files_changed: 4
---

# Phase 3 Plan 03: Graph Traversal Endpoint Summary

**One-liner:** Depth-2 procurement network subgraph via explicit two-layer Cypher expansion with 30s timeout, 300-node/500-edge hard caps, privacy filtering, semantic Spanish edge labels, and 10 req/min rate limiting at GET /api/v1/graph/{id}.

## What Was Built

### Task 1: Graph Response Models (`api/models/graph.py`)

Three Pydantic models targeting the Sigma.js/graphology node-link format used by Phase 4 frontend:

**NodeDTO** — single node in the subgraph:
- `id: str` — canonical business key (nit, cedula, id_contrato, codigo_entidad)
- `label: str` — Neo4j label (Empresa, Persona, Contrato, EntidadPublica, Sancion)
- `properties: dict` — privacy-filtered node properties

**EdgeDTO** — single relationship:
- `source: str` / `target: str` — node IDs (directed)
- `type: str` — relationship type (EJECUTA, ADJUDICO, SANCIONO, REPRESENTA, EMPLEA, PARTICIPO)
- `properties: dict` — relationship properties including `_label` Spanish semantic label

**GraphResponse** — full subgraph:
- `nodes: list[NodeDTO]` — deduplicated, privacy-filtered
- `edges: list[EdgeDTO]` — all connecting relationships
- `truncated: bool` — True when cut at MAX_NODES or MAX_EDGES
- `root_id: str` — root entity ID for client-side centering in Sigma.js

### Task 2: Graph Traversal Service (`api/services/graph_service.py`)

`get_subgraph(id, session, privacy)` implements two-phase expansion:

**Phase 0: Root resolution**
```cypher
MATCH (root)
WHERE root.nit = $id OR root.cedula = $id
   OR root.id_contrato = $id OR root.codigo_entidad = $id
RETURN root, labels(root)[0] AS label
LIMIT 1
```
Returns `None` if no entity found — router converts to HTTP 404.

**Phase 1 + 2: Two-layer expansion (single transaction, 30s timeout)**

Layer 1 — direct neighbors of root:
```cypher
MATCH (root)-[r1]-(n1)
WHERE [root identifier predicates]
RETURN labels(n1)[0], properties(n1), type(r1), properties(r1),
       startNode(r1) = root AS r1_from_root
LIMIT $MAX_NODES
```

Layer 2 — neighbors of layer-1 nodes, excluding root:
```cypher
MATCH (n1)-[r2]-(n2)
WHERE (n1.nit IN $ids OR ...)
  AND NOT (n2.nit = $root_id OR ...)
RETURN labels(n2)[0], properties(n2), type(r2), properties(r2), n1_id
LIMIT $remaining_budget
```

**Constants:**
| Constant | Value | Rationale |
|----------|-------|-----------|
| MAX_NODES | 300 | Readable in Sigma.js force-directed layout without browser pressure |
| MAX_EDGES | 500 | Keeps graph sparse enough for meaningful pattern detection |
| QUERY_TIMEOUT | 30.0s | Balances complex network traversal against user experience |

**Privacy filtering:** `privacy.filter_node(label, props)` called for every node added to the result dict — consistent with 03-01 PrivacyFilter pattern.

**Edge labels (PRIV-03):** Every edge gets `_label` in its properties dict:
| Relationship | _label |
|-------------|--------|
| EJECUTA | ejecuta contrato |
| ADJUDICO | adjudico contrato |
| SANCIONO | recibio sancion |
| REPRESENTA | representa empresa |
| EMPLEA | emplea a funcionario |
| PARTICIPO | participo en proceso |
| RELACIONADO_CON | relacionado con |

**Timeout handling:** Neo4j `ClientError` with `"TransactionTimedOut"` in message is re-raised as `TimeoutError` — router catches and returns HTTP 408.

### Task 3: Graph Router + Final main.py (`api/routers/graph.py`, `api/main.py`)

**`api/routers/graph.py` — GET /api/v1/graph/{id}:**
- `@limiter.limit("10/minute")` — most expensive endpoint, tightest rate limit
- Catches `TimeoutError` → HTTP 408 with actionable message
- Returns HTTP 404 when `get_subgraph()` returns None
- Wraps `GraphResponse(**subgraph)` in `APIResponse` envelope with `meta.fuentes` freshness block
- No Cypher in the handler — all traversal logic in service layer

**`api/main.py` — Final Phase 3 state:**

All five Phase 3 routers registered:
```python
app.include_router(health_router, prefix="")
app.include_router(search_router, prefix="/api/v1")
app.include_router(contractors_router, prefix="/api/v1")
app.include_router(contracts_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")
```

## Complete Phase 3 API Surface

| Endpoint | Rate Limit | Requirement | Plan |
|----------|-----------|-------------|------|
| `GET /health` | None | Phase 1 | 03-01 |
| `GET /api/v1/search` | 60/min | API-01 | 03-01 |
| `GET /api/v1/contractor/{id}` | 30/min | API-02 | 03-02 |
| `GET /api/v1/contract/{id}` | 60/min | API-03 | 03-02 |
| `GET /api/v1/graph/{id}` | 10/min | API-04 | 03-03 |

## Graph Expansion Strategy

### Why Two-Layer vs [*..2]

`MATCH (root)-[*..2]-(n)` generates all paths up to depth 2. For a contractor with 500 contracts, each connected to an entidad and competing oferentes, this produces O(n²) intermediate path results before deduplication. On dense networks (large NITs with thousands of contracts) this can exhaust Neo4j heap.

The explicit two-layer approach:
1. Layer 1: `MATCH (root)-[r1]-(n1)` — bounded by `LIMIT MAX_NODES` upfront
2. Layer 2: Uses the layer-1 ID list as input — bounded by remaining node budget

Total Neo4j work is proportional to nodes returned, not paths found.

## Verification Results

All automated checks passed:

```
models/graph.py: NodeDTO defined                              PASS
models/graph.py: EdgeDTO defined                             PASS
models/graph.py: truncated bool field present                PASS
graph_service.py: begin_transaction(timeout=...) present     PASS
graph_service.py: MAX_NODES defined                          PASS
graph_service.py: truncated flag present                     PASS
graph_service.py: filter_node() called                       PASS
routers/graph.py: @limiter.limit("10/minute")                PASS
routers/graph.py: HTTP 408 on TimeoutError                   PASS
main.py: graph_router registered                             PASS
main.py: 5 include_router calls total                        PASS
```

Live stack verification (requires `docker compose up -d` + data loaded) not run — no running Neo4j instance with data available in this execution environment.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All endpoint logic is fully wired. The `meta.fuentes` array correctly returns empty when no ETL SourceIngestion nodes exist (populated by Phase 2 pipelines at runtime).

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | adbd98b | feat(03-03): add NodeDTO, EdgeDTO, GraphResponse Pydantic models |
| 2 | ef5885a | feat(03-03): add graph traversal service with two-layer expansion |
| 3 | e0feb9b | feat(03-03): add graph router and register all five routes in main.py |
