# Phase 4 Context: Frontend and Pattern Detection

**Phase:** 04  
**Name:** Frontend and Pattern Detection  
**Captured:** 2026-04-09  
**Depends on:** Phase 3 (Backend API)  
**Requirements:** UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08, PAT-01, PAT-02, PAT-03, PAT-04, PAT-05

---

## Goal

Investigators can search for any entity, view their procurement network, see red flags, and trace every data point to its source — all in Spanish.

---

## Success Criteria

1. A user can type a NIT, cedula, or name and land on a contractor profile page showing contracts, sanctions, and red flags
2. Red flag badges (single bidder, short tender window, inflated contract, direct award concentration, sanctioned contractor) appear on relevant records
3. The interactive WebGL graph explorer renders the procurement network around any entity and allows clicking nodes to navigate
4. Every data point on screen shows its source and ingestion date, with no bare assertions of relationships
5. The entire interface is in Spanish and renders correctly on desktop viewport widths

---

## Technology Decisions

### Frontend Framework
- **React 19 + Vite 8 + TypeScript 5** — current stable stack; React 19 compiler optimizations reduce re-render cost for graph-heavy UIs; Vite 8 uses Oxc for React Refresh (no Babel, faster HMR)
- No alternatives considered — locked in STACK.md research

### Graph Visualization
- **@react-sigma/core 5.0.x + graphology 0.25.x** — Sigma.js v3 WebGL renderer; handles 10,000+ nodes smoothly; mandatory for Colombian contractor networks that will be large; Sigma.js is the library used by OCCRP Aleph and other investigative journalism graph tools
- **@react-sigma/layout-forceatlas2** for force-directed layout
- Alternative react-force-graph rejected: Canvas renderer, degrades above 2K nodes

### Styling
- **Tailwind CSS 4.x** — utility-first, zero-runtime; native CSS variables in v4; no component library needed — UI is primarily graph canvas + search inputs
- All visual decisions (color palette, typography, layout) deferred to executing agent (YOLO mode: user wants it built, not debated)

### State / Data Fetching
- **TanStack Query 5.x** — server state management, caching, background refresh, loading states for graph query results
- **React Router 6.x** — client-side routing; file-based routing for search, profile, contract detail, graph explorer pages

### API Client
- Typed fetch wrapper over the Phase 3 FastAPI endpoints (`/api/v1/search`, `/api/v1/entities/{id}`, `/api/v1/contracts/{id}`, `/api/v1/graph/{id}`, `/api/v1/meta`)
- All API responses typed as TypeScript interfaces matching FastAPI Pydantic models

### Pattern Detection (Backend Batch Job)
- Red flags run as **batch Cypher queries** executed by a Python script (part of the ETL/API layer, not the frontend)
- Results stored as **node properties** on Contrato/Proceso nodes in Neo4j (e.g., `flag_single_bidder: true`, `flag_short_tender: true`)
- FastAPI API returns flags as part of contract/profile responses — frontend only reads and displays
- No real-time pattern computation on the frontend or in the API request path

---

## Pages and Views

### 1. Search Landing Page (UI-01)
- Prominent search bar centered on page
- Accepts: NIT (empresa), cedula (persona), or free-text name
- Search-first design: no clutter, no dashboard widgets on the landing page
- Results list below the search bar: entity name, type, NIT/cedula, matching score
- Quick filters: Empresa / Persona / EntidadPublica

### 2. Contractor Profile Page (UI-02, UI-05, UI-06)
- Entity header: name, NIT/cedula, type badge, data freshness timestamp
- Red flag summary bar: count and types of flags on this entity
- Contracts table: paginated, sortable by value/date, each row with flag badges
- Sanctions section: SIRI sanctions linked to this entity (if any)
- Related entities sidebar: other entities linked via EJECUTA, ADJUDICO, SANCIONO
- Provenance footer per data block: `Fuente: rpmr-utcd | Actualizado: 2026-04-01`

### 3. Contract Detail Page (UI-03, UI-05, UI-06)
- Full SECOP field display: valor, entidad, modalidad, plazo, objeto, numero oferentes
- Red flag badges with explanation tooltips (what triggered the flag and why it matters)
- Provenance block: dataset, ingestion timestamp, SECOP URL link
- Links to contractor profile and entidad profile

### 4. Interactive Graph Explorer (UI-04)
- WebGL canvas (Sigma.js) rendering procurement network around a selected entity
- Node types distinguished by color/shape: Empresa (blue circle), Persona (green diamond), EntidadPublica (orange square), Contrato (grey dot), Sancion (red triangle)
- Depth selector: 1 / 2 hops (capped at depth=2 per API design)
- Click node: sidebar panel opens with entity summary and link to full profile
- Hover edge: tooltip showing relationship type and source
- Zoom, pan, minimap controls

### 5. No Dedicated Admin / Settings Page
- Stack is configured entirely via environment variables (PUBLIC_MODE, etc.)
- No user accounts, no RBAC (per out-of-scope decisions in REQUIREMENTS.md)

---

## Red Flag Detectors

All five flags are implemented as batch Cypher queries. Results are stored as boolean properties on the relevant node and returned by the API. Frontend displays badges — it does not compute flags.

### PAT-01: Oferente Unico (Single Bidder)
- **Trigger:** Proceso with modalidad = competitive AND numero_oferentes = 1
- **Cypher target:** `Proceso` node → property `flag_oferente_unico: true`
- **Data required:** `numero_oferentes` field from SECOP Integrado / SECOP II Procesos
- **Badge label:** "Oferente Unico"
- **Tooltip:** "Solo se recibio una oferta en este proceso competitivo"

### PAT-02: Periodo de Licitacion Corto (Short Tender Window)
- **Trigger:** Proceso where (fecha_cierre - fecha_publicacion) < 5 calendar days
- **Cypher target:** `Proceso` node → property `flag_periodo_corto: true`
- **Data required:** `fecha_publicacion`, `fecha_cierre` from SECOP II Procesos
- **Threshold:** 5 days (configurable constant in batch script)
- **Badge label:** "Licitacion Corta"
- **Tooltip:** "El periodo de publicacion del proceso fue inferior a 5 dias"

### PAT-03: Adicion al Valor del Contrato (Contract Amendment Inflation)
- **Trigger:** Contrato where valor_final > valor_adjudicado * 1.20 (>20% over awarded value)
- **Cypher target:** `Contrato` node → property `flag_adicion_valor: true`, `flag_adicion_pct: <float>`
- **Data required:** `valor_contrato` at award + addenda records from SECOP
- **Threshold:** 20% over awarded value (configurable constant)
- **Badge label:** "Adicion de Valor"
- **Tooltip:** "El valor final del contrato supera en X% el valor adjudicado originalmente"

### PAT-04: Concentracion de Contratacion Directa (Direct Award Concentration)
- **Trigger:** Empresa receiving > 50% of a single EntidadPublica's direct-award contracts by value in a rolling 12-month window
- **Cypher target:** `Empresa` node → property `flag_concentracion_directa: true`, `flag_concentracion_entidades: [list of entidad NITs]`
- **Data required:** `modalidad_contratacion = "Contratacion Directa"`, aggregated by entidad
- **Threshold:** 50% of entity direct-award budget (configurable constant)
- **Badge label:** "Concentracion Directa"
- **Tooltip:** "Este contratista recibe mas del 50% de las adjudicaciones directas de una entidad"

### PAT-05: Contratista Sancionado (Sanctioned Contractor)
- **Trigger:** Empresa or Persona with an active Sancion linked via SANCIONO relationship AND at least one Contrato with fecha_fin > today
- **Cypher target:** `Empresa`/`Persona` node → property `flag_contratista_sancionado: true`
- **Data required:** `Sancion` nodes from SIRI/SECOP Multas + `Contrato` fecha_fin
- **Badge label:** "Contratista Sancionado"
- **Tooltip:** "Este contratista tiene sanciones activas y contratos en ejecucion"

---

## Architecture Decisions

### Frontend File Structure
```
frontend/src/
├── api/                  # Typed API client (fetch wrappers)
│   ├── client.ts         # Base fetch with error handling
│   ├── search.ts         # /api/v1/search
│   ├── entities.ts       # /api/v1/entities/{id}
│   ├── contracts.ts      # /api/v1/contracts/{id}
│   ├── graph.ts          # /api/v1/graph/{id}
│   └── meta.ts           # /api/v1/meta (freshness)
├── components/
│   ├── layout/           # AppShell, Header, Footer
│   ├── search/           # SearchBar, SearchResults, EntityCard
│   ├── profile/          # ProfileHeader, ContractTable, SancionList, RelatedEntities
│   ├── contract/         # ContractDetail, ContractFields, RedFlagBadge
│   ├── graph/            # GraphExplorer, NodeSidebar, GraphControls
│   ├── common/           # Provenance, FreshnessIndicator, LoadingState, ErrorState
│   └── flags/            # FlagBadge, FlagTooltip, FlagSummaryBar
├── pages/
│   ├── BuscarPage.tsx    # / — search landing
│   ├── PerfilPage.tsx    # /perfil/:id — contractor profile
│   ├── ContratoPage.tsx  # /contrato/:id — contract detail
│   └── GrafoPage.tsx     # /grafo/:id — graph explorer
├── types/                # TypeScript interfaces for API responses
│   ├── entities.ts
│   ├── contracts.ts
│   ├── graph.ts
│   └── flags.ts
├── hooks/                # Custom React hooks
│   ├── useSearch.ts
│   ├── useEntity.ts
│   ├── useGraph.ts
│   └── useContract.ts
├── App.tsx
└── main.tsx
```

### Pattern Detection Batch Script Structure
```
etl/pattern_detection/
├── __init__.py
├── run_flags.py          # CLI: python -m etl.pattern_detection.run_flags [--source all|pat01|...]
├── queries/
│   ├── pat01_single_bidder.cypher
│   ├── pat02_short_tender.cypher
│   ├── pat03_contract_amendment.cypher
│   ├── pat04_direct_award_concentration.cypher
│   └── pat05_sanctioned_contractor.cypher
└── detector.py           # PatternDetector class, executes queries and writes results
```

### Nginx Routing (already in place)
- `/` → React SPA (index.html, client-side routing handles all sub-routes)
- `/api/` → FastAPI backend (proxy_pass http://api:8000/)
- No changes to `frontend/nginx.conf` or `frontend/Dockerfile` structure — build process stays the same (Vite build → /app/dist → nginx static)

---

## Language and Localization

- **Spanish only.** No i18n library, no locale files, no translation layer.
- All UI labels, tooltips, error messages, and help text written directly in Spanish.
- Justification: target users are Colombian; English UI creates adoption friction; i18n adds complexity with zero benefit for v1.

---

## Responsive / Mobile Policy

- **Desktop-first responsive web.** Minimum target: 1280px wide viewport.
- Must render correctly on 1024px+ (laptop). 
- Mobile is out of scope (per REQUIREMENTS.md and PROJECT.md): no native app, no mobile-optimized layout required.
- Graph explorer (WebGL canvas) is inherently desktop-only; this is acceptable.

---

## Visual Design Choices (YOLO Mode)

User explicitly requested no design debates — executing agent has full discretion on:
- Color palette (dark/light mode, primary/accent colors)
- Typography (font family, size scale)
- Component visual design (card style, table density, badge shapes)
- Graph node/edge colors and shapes
- Animation and transition timing

Constraint: must be readable, professional, and appropriate for investigative journalism context. Avoid frivolous decorative elements.

---

## Plans

| Plan | Wave | Focus |
|------|------|-------|
| 04-01 | 1 | React + Vite scaffold, project structure, API client, search landing page |
| 04-02 | 1 | Red flag Cypher queries + batch detector script (pattern detection backend) |
| 04-03 | 2 | Contractor profile page, contract detail page, graph explorer, red flag badges |

Wave 1 plans (04-01 and 04-02) are independent and can execute in parallel.  
Wave 2 plan (04-03) depends on 04-01 (frontend scaffold) and 04-02 (flags stored in Neo4j).

---

## Key Interfaces with Phase 3

Phase 4 consumes the FastAPI endpoints built in Phase 3. These are the contracts the frontend depends on:

| Endpoint | Used by |
|----------|---------|
| `GET /api/v1/search?q=&type=` | SearchBar → BuscarPage |
| `GET /api/v1/entities/{id}` | PerfilPage |
| `GET /api/v1/contracts/{id}` | ContratoPage |
| `GET /api/v1/graph/{id}?depth=` | GrafoPage |
| `GET /api/v1/meta` | FreshnessIndicator (header) |

Red flags are returned as properties on entity/contract responses — no dedicated flag endpoint needed.

---

## Deferred to v2

- Mobile-optimized layout
- Dark mode toggle (executing agent may implement if trivial; not required)
- CSV/JSON export of search results (ADV-03)
- Cypher query builder for advanced users (ADV-01)
- Concentration analysis dashboards
- PAT-06 (newly-created company) — requires RUES data not in v1
- PAT-07 (conflict of interest detection) — requires SIGEP + RUES cross-link

---

*Context captured: 2026-04-09*  
*Sources: .planning/ROADMAP.md, .planning/REQUIREMENTS.md, .planning/PROJECT.md, .planning/research/STACK.md, .planning/research/FEATURES.md, .planning/research/ARCHITECTURE.md*
