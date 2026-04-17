---
phase: 04-frontend-and-pattern-detection
plan: "01"
subsystem: frontend
tags: [react, vite, typescript, tailwind, tanstack-query, react-sigma, search-ui]
dependency_graph:
  requires:
    - "03-backend-api (FastAPI endpoints: /search, /entities, /contracts, /graph, /meta)"
  provides:
    - "frontend/src/api/* — typed API client for all five endpoints"
    - "frontend/src/types/* — TypeScript interfaces matching FastAPI Pydantic models"
    - "frontend/src/hooks/* — TanStack Query hooks with enabled guards"
    - "frontend/src/pages/BuscarPage.tsx — search landing page UI-01"
    - "frontend/src/components/layout/* — AppShell + Header with FreshnessIndicator"
    - "frontend/src/components/search/* — SearchBar, TypeFilter, SearchResults, EntityCard"
    - "frontend/src/components/flags/FlagBadge.tsx — shared flag badge for Plan 04-03"
  affects:
    - "04-02 (pattern detection) — consumes flag types from types/flags.ts"
    - "04-03 (profiles, graph) — builds on AppShell, hooks, types, FlagBadge, stub pages"
tech_stack:
  added:
    - "React 19.2.5"
    - "Vite 8.0.8"
    - "TypeScript 5.9.3"
    - "Tailwind CSS 4.2.2 (via @tailwindcss/vite plugin)"
    - "@react-sigma/core 5.0.6 + sigma 3.0.2 + graphology 0.26.0"
    - "@tanstack/react-query 5.97.0"
    - "react-router-dom 6.30.3"
    - "@vitejs/plugin-react 5.x (Vite 8 compatible)"
  patterns:
    - "TanStack Query with enabled guard for optional ID parameters"
    - "Debounced search input (300ms) with useEffect + setTimeout"
    - "Lazy-loaded heavy pages (Sigma.js ~400KB) via React.lazy + Suspense"
    - "apiFetch wrapper with ApiError class for consistent error handling"
    - "Spanish-only user-facing strings throughout all components"
key_files:
  created:
    - frontend/package.json
    - frontend/vite.config.ts
    - frontend/tsconfig.json
    - frontend/tsconfig.app.json
    - frontend/index.html
    - frontend/src/main.tsx
    - frontend/src/index.css
    - frontend/src/App.tsx
    - frontend/src/api/client.ts
    - frontend/src/api/search.ts
    - frontend/src/api/entities.ts
    - frontend/src/api/contracts.ts
    - frontend/src/api/graph.ts
    - frontend/src/api/meta.ts
    - frontend/src/types/flags.ts
    - frontend/src/types/entities.ts
    - frontend/src/types/contracts.ts
    - frontend/src/types/graph.ts
    - frontend/src/hooks/useSearch.ts
    - frontend/src/hooks/useEntity.ts
    - frontend/src/hooks/useContract.ts
    - frontend/src/hooks/useGraph.ts
    - frontend/src/components/layout/AppShell.tsx
    - frontend/src/components/layout/Header.tsx
    - frontend/src/components/common/FreshnessIndicator.tsx
    - frontend/src/components/common/LoadingState.tsx
    - frontend/src/components/common/ErrorState.tsx
    - frontend/src/components/common/Provenance.tsx
    - frontend/src/components/search/SearchBar.tsx
    - frontend/src/components/search/TypeFilter.tsx
    - frontend/src/components/search/SearchResults.tsx
    - frontend/src/components/search/EntityCard.tsx
    - frontend/src/components/flags/FlagBadge.tsx
    - frontend/src/pages/BuscarPage.tsx
    - frontend/src/pages/PerfilPage.tsx (stub)
    - frontend/src/pages/ContratoPage.tsx (stub)
    - frontend/src/pages/GrafoPage.tsx (stub)
  modified: []
decisions:
  - "graphology pinned to ^0.26.0 (not ^0.25.4 as planned) to satisfy @react-sigma/core@5.0.6 peer dependency"
  - "@vitejs/plugin-react bumped to ^5.0.0 for Vite 8 compatibility (^4.x does not support Vite 8)"
  - "@react-sigma/core CSS imported via lib/style.css (not index.css — correct exports field path in v5)"
  - "Stub pages PerfilPage, ContratoPage, GrafoPage created for Plan 04-03 to replace"
metrics:
  duration: "6 minutes"
  completed_date: "2026-04-09"
  tasks_completed: 4
  files_created: 37
---

# Phase 4 Plan 1: Frontend Scaffold + Search Landing Page Summary

React 19 + Vite 8 + TypeScript 5 + Tailwind 4 frontend fully scaffolded with typed API client, TanStack Query hooks, AppShell layout, and BuscarPage search landing page (UI-01).

## What Was Built

### Task 1: Project Scaffold

Complete React + Vite project wired up without running `npm create vite` to preserve the existing `Dockerfile` and `nginx.conf`:

- `package.json` — all Phase 4 dependencies pinned
- `vite.config.ts` — `@tailwindcss/vite` plugin, `/api` proxy to `localhost:8000`, `@/*` path alias
- `tsconfig.app.json` — strict mode, `noUnusedLocals`, `noUnusedParameters`, `@/*` paths
- `index.html` — `lang="es"`, Spanish meta description
- `src/main.tsx` — `QueryClientProvider` with `staleTime: 5 * 60 * 1000`
- `src/index.css` — `@import "tailwindcss"` + `.sigma-container` utility class

### Task 2: Types + API Client + Hooks

14 files establishing the typed API layer:

- `types/flags.ts` — `RedFlagName` union (5 flags) + `RED_FLAG_METADATA` record with Spanish labels/descriptions
- `types/entities.ts` — `EntitySummary`, `ContractorProfile`, `SearchResponse`, `MetaResponse`
- `types/contracts.ts` — `ContractSummary`, `ContractDetail`
- `types/graph.ts` — `GraphNode`, `GraphEdge`, `GraphResponse`
- `api/client.ts` — `apiFetch<T>` generic wrapper, `ApiError` class, `BASE = "/api/v1"`
- `api/search.ts`, `entities.ts`, `contracts.ts`, `graph.ts`, `meta.ts` — one function per endpoint using `apiFetch`
- `hooks/useSearch.ts` — `enabled: q.trim().length >= 2`
- `hooks/useEntity.ts`, `useContract.ts` — `enabled: Boolean(id)`
- `hooks/useGraph.ts` — `enabled: Boolean(id)`, 10-minute `staleTime`

### Task 3: AppShell + Layout Components

- `AppShell.tsx` — `min-h-screen flex flex-col` with Header + main + footer
- `Header.tsx` — dark `slate-900` bar with HunterLeech link + `FreshnessIndicator`
- `FreshnessIndicator.tsx` — queries `/api/v1/meta`, shows oldest source date in `es-CO` locale
- `LoadingState.tsx` — spinner with configurable `mensaje` prop (Spanish default)
- `ErrorState.tsx` — "Error al cargar los datos" + optional reintentar button
- `Provenance.tsx` — maps Socrata dataset IDs to Spanish source labels

### Task 4: Search Page + Routing

- `FlagBadge.tsx` — danger (red) / warning (amber) flag chips using `RED_FLAG_METADATA`
- `SearchBar.tsx` — 300ms debounce via `useEffect` + `setTimeout`; "Limpiar busqueda" clear button
- `TypeFilter.tsx` — "Todos" + Empresa / Persona / Entidad Publica pills with active state
- `EntityCard.tsx` — links to `/perfil/:id`, shows nombre, NIT/CC, type badge, flag badges
- `SearchResults.tsx` — loading/error/empty/results states all in Spanish
- `BuscarPage.tsx` — hero landing when idle, search + filter + results when query >= 2 chars
- `App.tsx` — `createBrowserRouter` with 4 routes; PerfilPage/ContratoPage/GrafoPage lazy-loaded

## Installed Package Versions

| Package | Version |
|---------|---------|
| react | 19.2.5 |
| @react-sigma/core | 5.0.6 |
| sigma | 3.0.2 |
| graphology | 0.26.0 |
| @tanstack/react-query | 5.97.0 |
| react-router-dom | 6.30.3 |
| vite | 8.0.8 |
| tailwindcss | 4.2.2 |
| typescript | 5.9.3 |

## File Tree

```
frontend/src/
├── App.tsx
├── index.css
├── main.tsx
├── api/
│   ├── client.ts
│   ├── contracts.ts
│   ├── entities.ts
│   ├── graph.ts
│   ├── meta.ts
│   └── search.ts
├── components/
│   ├── common/
│   │   ├── ErrorState.tsx
│   │   ├── FreshnessIndicator.tsx
│   │   ├── LoadingState.tsx
│   │   └── Provenance.tsx
│   ├── flags/
│   │   └── FlagBadge.tsx
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   └── Header.tsx
│   └── search/
│       ├── EntityCard.tsx
│       ├── SearchBar.tsx
│       ├── SearchResults.tsx
│       └── TypeFilter.tsx
├── hooks/
│   ├── useContract.ts
│   ├── useEntity.ts
│   ├── useGraph.ts
│   └── useSearch.ts
├── pages/
│   ├── BuscarPage.tsx        ← implemented (UI-01)
│   ├── ContratoPage.tsx      ← stub for Plan 04-03
│   ├── GrafoPage.tsx         ← stub for Plan 04-03
│   └── PerfilPage.tsx        ← stub for Plan 04-03
└── types/
    ├── contracts.ts
    ├── entities.ts
    ├── flags.ts
    └── graph.ts
```

## TypeScript Build Result

```
tsc --noEmit: 0 errors
npm run build: exit 0
  87 modules transformed
  dist/ produced in 408ms
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] graphology peer dependency version mismatch**
- **Found during:** Overall build verification (npm install)
- **Issue:** Plan specified `graphology@^0.25.4` but `@react-sigma/core@5.0.6` requires `graphology@^0.26.0` — npm ERESOLVE error
- **Fix:** Updated `package.json` `graphology` to `^0.26.0`; installed version is `0.26.0`
- **Files modified:** `frontend/package.json`
- **Commit:** 56dc5ca

**2. [Rule 1 - Bug] @vitejs/plugin-react version incompatible with Vite 8**
- **Found during:** Overall build verification (npm install)
- **Issue:** `@vitejs/plugin-react@^4.3.0` peer dep requires `vite@^4.2.0 || ^5.0.0 || ^6.0.0 || ^7.0.0` — does not include Vite 8
- **Fix:** Updated to `@vitejs/plugin-react@^5.0.0` which supports Vite 8
- **Files modified:** `frontend/package.json`
- **Commit:** 56dc5ca

**3. [Rule 1 - Bug] @react-sigma/core CSS import path incorrect**
- **Found during:** `npm run build` (vite build phase)
- **Issue:** `import '@react-sigma/core/index.css'` fails — the package exports field maps CSS as `./lib/style.css`, not `./index.css`
- **Fix:** Changed import to `import '@react-sigma/core/lib/style.css'`
- **Files modified:** `frontend/src/main.tsx`
- **Commit:** 56dc5ca

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `PerfilPage` | `frontend/src/pages/PerfilPage.tsx` | Contractor/entity profile page — implemented in Plan 04-03 |
| `ContratoPage` | `frontend/src/pages/ContratoPage.tsx` | Contract detail page — implemented in Plan 04-03 |
| `GrafoPage` | `frontend/src/pages/GrafoPage.tsx` | Graph explorer with Sigma.js — implemented in Plan 04-03 |

These stubs render Spanish placeholder text and do not affect Plan 04-01's goal (BuscarPage search landing). Plan 04-03 replaces all three stubs.

## Self-Check: PASSED

- frontend/package.json: FOUND
- frontend/src/api/client.ts: FOUND (BASE = "/api/v1")
- frontend/src/types/flags.ts: FOUND (5 RedFlagName values + RED_FLAG_METADATA)
- frontend/src/pages/BuscarPage.tsx: FOUND (uses useSearch)
- frontend/src/App.tsx: FOUND (createBrowserRouter, 4 routes, lazy loading)
- Commits: a785efd, 7b4d48c, 485e1ab, 43b61ae, 56dc5ca all present
- npm run build: exit 0, 87 modules, dist/ produced
