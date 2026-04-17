---
phase: 04-frontend-and-pattern-detection
plan: "03"
subsystem: frontend
tags: [react, sigma, graphology, forceatlas2, profile-page, contract-detail, graph-explorer, red-flags]
dependency_graph:
  requires:
    - "04-01 (AppShell, hooks, types, FlagBadge, stub pages)"
    - "04-02 (pattern detection writes flags to Neo4j nodes consumed by API)"
    - "03-backend-api (FastAPI /entities/:id, /contracts/:id, /graph/:id endpoints)"
  provides:
    - "frontend/src/pages/PerfilPage.tsx — contractor profile page (UI-02)"
    - "frontend/src/pages/ContratoPage.tsx — contract detail page (UI-03)"
    - "frontend/src/pages/GrafoPage.tsx — interactive graph explorer (UI-04)"
    - "frontend/src/components/flags/FlagSummaryBar.tsx — shared flag bar"
    - "frontend/src/components/profile/* — 5 profile sub-components"
    - "frontend/src/components/contract/* — 2 contract sub-components"
    - "frontend/src/components/graph/* — 4 graph sub-components"
  affects:
    - "Complete journalist investigation flow: search → profile → contract → graph"
tech_stack:
  added: []
  patterns:
    - "SigmaContainer with nested GraphLoader (useLoadGraph) and EventHandler (useRegisterEvents/useSigma)"
    - "ForceAtlas2 layout assigned after 100ms delay to ensure Sigma has mounted"
    - "MultiDirectedGraph from graphology with per-type color/size node attributes"
    - "Intl.NumberFormat es-CO COP currency formatting (zero fraction digits)"
    - "Conditional /perfil links — only Empresa/Persona/EntidadPublica node types navigate"
key_files:
  created:
    - frontend/src/components/flags/FlagSummaryBar.tsx
    - frontend/src/components/profile/ProfileHeader.tsx
    - frontend/src/components/profile/SancionCard.tsx
    - frontend/src/components/profile/SancionList.tsx
    - frontend/src/components/profile/ContractRow.tsx
    - frontend/src/components/profile/ContractTable.tsx
    - frontend/src/components/profile/RelatedEntities.tsx
    - frontend/src/components/contract/ContractFields.tsx
    - frontend/src/components/contract/ContractDetail.tsx
    - frontend/src/components/graph/GraphLoader.tsx
    - frontend/src/components/graph/NodeSidebar.tsx
    - frontend/src/components/graph/GraphControls.tsx
    - frontend/src/components/graph/GraphExplorer.tsx
  modified:
    - frontend/src/pages/PerfilPage.tsx (stub replaced)
    - frontend/src/pages/ContratoPage.tsx (stub replaced)
    - frontend/src/pages/GrafoPage.tsx (stub replaced)
decisions:
  - "labelRenderedSizeThreshold (not labelThreshold) is the correct Sigma v3 Settings property — plan template had wrong name"
metrics:
  duration: "4min"
  completed_date: "2026-04-10"
  tasks_completed: 4
  files_created: 16
---

# Phase 4 Plan 03: Profile, Contract, and Graph Explorer Pages Summary

Three full-implementation pages replacing all Plan 04-01 stubs: contractor profile with flag summary bar and contracts table, contract detail with all SECOP fields and COP formatting, and Sigma.js WebGL graph explorer with ForceAtlas2 layout and click-to-select node sidebar.

## What Was Built

### Task 1: Flag Summary Bar + Profile Components

8 files completing the contractor profile page:

- `FlagSummaryBar.tsx` — horizontal flag badge row; shows green "Sin alertas detectadas" when flags array is empty
- `ProfileHeader.tsx` — name, NIT/cedula identifier, entity type badge (Empresa/Persona/Entidad), FlagSummaryBar, "Ver en grafo" link, data freshness line
- `SancionCard.tsx` — red color scheme card (border-red-200/bg-red-50) with tipo, autoridad, fecha, descripcion, fuente
- `SancionList.tsx` — maps SancionSummary[] to SancionCard list; empty-state message in Spanish
- `ContractRow.tsx` — table row linking to `/contrato/:id`, COP-formatted valor via `Intl.NumberFormat("es-CO")`, flag badges per contract
- `ContractTable.tsx` — HTML table with 6 Spanish column headers; empty-state message
- `RelatedEntities.tsx` — linked entity cards to `/perfil/:id`, shows up to 2 flag badges + overflow count
- `PerfilPage.tsx` — replaces stub; uses `useEntity(id)` hook; 2-col layout (contracts main + related sidebar); conditional sanctions section

### Task 2: Contract Detail Page

3 files for the contract detail view:

- `ContractFields.tsx` — `FieldRow` sub-component renders all SECOP fields: valor (COP), valor_adjudicado with % delta, modalidad, numero_oferentes, 3 dates (es-CO long locale), entidad link, contratista link, optional SECOP URL
- `ContractDetail.tsx` — composes ContractFields + FlagBadge array (prominent, before field grid) + Provenance at bottom
- `ContratoPage.tsx` — replaces stub; uses `useContract(id)` hook; full loading/error states in Spanish

### Task 3: Sigma.js Graph Explorer

5 files for the interactive graph:

- `GraphLoader.tsx` — `useLoadGraph` + `useLayoutForceAtlas2(150 iterations)`; 5-type color map (blue/green/amber/gray/red) and size map (6–14); random initial positions; edge guard for missing source/target; 100ms layout delay
- `NodeSidebar.tsx` — absolute-positioned panel (top-4 right-4); node label, NIT, type badge, flag badges; "Ver perfil completo" link only for Empresa/Persona/EntidadPublica
- `GraphControls.tsx` — depth 1/2 toggle buttons + node/edge count display in Spanish
- `GraphExplorer.tsx` — `SigmaContainer` wrapping `GraphLoader` + `EventHandler`; `EventHandler` uses `useRegisterEvents` + `useSigma` (correctly nested inside SigmaContainer); `clickNode` sets selected node; `clickStage` clears selection
- `GrafoPage.tsx` — replaces stub; `useState<1|2>(2)` for depth; `useGraph(id, depth)` re-fetches on depth change; full-viewport height layout

### Task 4: TypeScript Build Verification

`npm run type-check` and `npm run build` both pass with 0 errors.

## TypeScript Build Result

```
tsc --noEmit: 0 errors
npm run build: exit 0
  128 modules transformed
  dist/ produced in 447ms
```

## Vite Bundle Sizes

| Chunk | Size | Gzip |
|-------|------|------|
| index.html | 0.73 kB | 0.42 kB |
| index.css | 24.46 kB | 5.55 kB |
| index.js (main) | 197.52 kB | 62.56 kB |
| GrafoPage.js | 182.18 kB | 44.31 kB |
| ErrorState.js | 100.84 kB | 33.13 kB |
| PerfilPage.js | 7.48 kB | 2.14 kB |
| ContratoPage.js | 4.32 kB | 1.62 kB |

GrafoPage is 182 kB (expected — Sigma.js WebGL renderer). All three page chunks are lazily loaded.

## Stub Pages Replaced

| Stub (Plan 04-01) | Replaced With |
|-------------------|---------------|
| `PerfilPage.tsx` ("Perfil — en construccion") | Full profile: ProfileHeader + ContractTable + SancionList + RelatedEntities |
| `ContratoPage.tsx` ("Detalle de contrato — en construccion") | Full detail: ContractDetail + ContractFields + Provenance |
| `GrafoPage.tsx` ("Explorador de grafo — en construccion") | Full graph: GraphExplorer + Sigma.js WebGL + NodeSidebar + GraphControls |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Sigma v3 settings property name `labelThreshold` → `labelRenderedSizeThreshold`**
- **Found during:** Task 4 — `npm run build` TypeScript compilation
- **Issue:** Plan specified `labelThreshold: 6` in `SigmaContainer` settings, but the Sigma v3 `Settings` type does not have this property. TypeScript error: `Object literal may only specify known properties, and 'labelThreshold' does not exist in type 'Partial<Settings<...>>'`
- **Fix:** Replaced with `labelRenderedSizeThreshold: 6` (verified in sigma dist source: `size < this.settings.labelRenderedSizeThreshold`)
- **Files modified:** `frontend/src/components/graph/GraphExplorer.tsx`
- **Commit:** a464267

## Known Stubs

None — all three pages are fully implemented. No placeholder data, no "en construccion" text, no empty components.

## Self-Check: PASSED

- frontend/src/components/flags/FlagSummaryBar.tsx: FOUND
- frontend/src/components/profile/ProfileHeader.tsx: FOUND
- frontend/src/components/profile/ContractTable.tsx: FOUND
- frontend/src/components/contract/ContractDetail.tsx: FOUND
- frontend/src/components/graph/GraphExplorer.tsx: FOUND (SigmaContainer + labelRenderedSizeThreshold)
- frontend/src/pages/PerfilPage.tsx: FOUND (useEntity, no stub text)
- frontend/src/pages/ContratoPage.tsx: FOUND (useContract, no stub text)
- frontend/src/pages/GrafoPage.tsx: FOUND (useGraph + depth state, no stub text)
- frontend/dist/index.html: FOUND
- Commits: 3a859bf, d7327bf, d06b7c8, a464267 all present
- npm run build: exit 0, 128 modules, dist/ produced
