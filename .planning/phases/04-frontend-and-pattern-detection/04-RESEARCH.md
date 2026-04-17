# Phase 4 Research: Frontend and Pattern Detection

**Phase:** 04  
**Researched:** 2026-04-09  
**Confidence:** HIGH (verified against npm, official docs, and SECOP data model)

---

## 1. @react-sigma/core Setup with graphology

### Package Installation

```bash
# Core graph visualization
npm install @react-sigma/core @react-sigma/layout-forceatlas2
npm install graphology graphology-types sigma

# Routing, state, styling
npm install @tanstack/react-query react-router-dom
npm install -D tailwindcss @tailwindcss/vite

# Version pins (April 2026)
# @react-sigma/core: 5.0.6
# graphology: 0.25.x
# sigma: 3.0.2
```

### Minimal Graph Component Pattern

@react-sigma/core wraps Sigma.js v3 in React context. The canonical setup uses `SigmaContainer` as the root, `useLoadGraph` hook to populate the graphology instance, and `useRegisterEvents` for interactivity.

```typescript
import { SigmaContainer, useLoadGraph, useRegisterEvents } from "@react-sigma/core";
import { MultiDirectedGraph } from "graphology";
import "@react-sigma/core/index.css";

interface GraphData {
  nodes: Array<{ id: string; label: string; type: string; x: number; y: number; size: number; color: string }>;
  edges: Array<{ id: string; source: string; target: string; label: string }>;
}

// Inner component has access to sigma context
function GraphLoader({ data }: { data: GraphData }) {
  const loadGraph = useLoadGraph();

  useEffect(() => {
    const graph = new MultiDirectedGraph();
    data.nodes.forEach(n => graph.addNode(n.id, { ...n }));
    data.edges.forEach(e => graph.addEdge(e.source, e.target, { label: e.label }));
    loadGraph(graph);
  }, [data, loadGraph]);

  return null;
}

function GraphExplorer({ data }: { data: GraphData }) {
  return (
    <SigmaContainer
      style={{ width: "100%", height: "600px" }}
      settings={{ renderEdgeLabels: true }}
    >
      <GraphLoader data={data} />
      <GraphEvents onNodeClick={(nodeId) => /* navigate to profile */ } />
    </SigmaContainer>
  );
}
```

### Force-Directed Layout

```typescript
import { useLayoutForceAtlas2 } from "@react-sigma/layout-forceatlas2";

function LayoutController() {
  const { assign } = useLayoutForceAtlas2({
    iterations: 100,
    settings: { gravity: 1, scalingRatio: 2 },
  });

  useEffect(() => { assign(); }, [assign]);
  return null;
}
```

### Node Type → Visual Encoding

| Node Label | Color | Shape (size hint) |
|-----------|-------|-------------------|
| Empresa | #3B82F6 (blue) | size 12 |
| Persona | #10B981 (green) | size 10 |
| EntidadPublica | #F59E0B (amber) | size 14 |
| Contrato | #6B7280 (grey) | size 6 |
| Sancion | #EF4444 (red) | size 8 |

Sigma.js uses `color`, `size`, and `label` as standard node attributes. Shape differentiation is done via custom renderer programs (optional in v1 — color differentiation alone is sufficient).

### API Response → graphology Format

FastAPI graph endpoint (`GET /api/v1/graph/{id}?depth=2`) will return:
```json
{
  "nodes": [
    { "id": "empresa:890399010", "label": "Construtech SAS", "type": "Empresa", "nit": "890399010", "flags": ["flag_oferente_unico"] }
  ],
  "edges": [
    { "id": "e1", "source": "empresa:890399010", "target": "contrato:C-123", "type": "EJECUTA", "fuente": "rpmr-utcd" }
  ]
}
```

Frontend maps `type` → `color`/`size` and places nodes using ForceAtlas2 layout (no pre-computed positions needed).

---

## 2. React Component Structure

### Routing (React Router 6)

```typescript
// App.tsx
import { createBrowserRouter, RouterProvider } from "react-router-dom";

const router = createBrowserRouter([
  { path: "/",              element: <BuscarPage /> },
  { path: "/perfil/:id",   element: <PerfilPage /> },
  { path: "/contrato/:id", element: <ContratoPage /> },
  { path: "/grafo/:id",    element: <GrafoPage /> },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
```

### TanStack Query Setup

```typescript
// main.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,  // 5 minutes — graph data changes nightly
      retry: 2,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <App />
  </QueryClientProvider>
);
```

### API Client Pattern

```typescript
// api/client.ts
const BASE = "/api/v1";

async function apiFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}

// api/search.ts
export const searchEntities = (q: string, type?: string) =>
  apiFetch<SearchResponse>("/search", { q, ...(type ? { type } : {}) });

// api/entities.ts
export const getEntity = (id: string) => apiFetch<EntityResponse>(`/entities/${id}`);

// Custom hooks
// hooks/useSearch.ts
export function useSearch(q: string) {
  return useQuery({
    queryKey: ["search", q],
    queryFn: () => searchEntities(q),
    enabled: q.length >= 2,
  });
}
```

### Search Page Component Structure

```
BuscarPage
├── AppShell (header with logo + meta freshness indicator)
├── SearchBar (controlled input, debounced, 300ms)
│   └── TypeFilter (Empresa | Persona | EntidadPublica toggles)
└── SearchResults
    └── EntityCard[] (name, type badge, NIT/cedula, flag count)
        └── link → /perfil/:id
```

### Profile Page Component Structure

```
PerfilPage
├── AppShell
├── ProfileHeader (name, NIT, type, freshness, flags summary bar)
├── FlagSummaryBar (horizontal list of red flag badges)
├── ContractsSection
│   ├── ContractTable (paginated, sortable)
│   │   └── ContractRow[] (valor, entidad, modalidad, fecha, flags badges)
│   │       └── link → /contrato/:id
│   └── GraphExplorerLink → /grafo/:id
├── SancionesSection (if any sanctions linked)
│   └── SancionCard[] (autoridad, tipo, fecha, fuente)
└── RelatedEntitiesSection
    └── EntityCard[] (linked via ADJUDICO/SANCIONO/EJECUTA)
```

### Contract Detail Component Structure

```
ContratoPage
├── AppShell
├── ContractHeader (numero, objeto, estado)
├── FlagBadgeList (all flags active on this contract)
├── ContractFields (two-column grid)
│   ├── valor_contrato (formatted COP)
│   ├── modalidad_contratacion
│   ├── plazo / fecha_inicio / fecha_fin
│   ├── numero_oferentes
│   └── entidad contratante link → /perfil/:entidad_id
├── ContratistaSummary (nombre, NIT, link → /perfil/:empresa_id)
└── ProvenanceBlock (fuente, dataset URL, ingestion timestamp)
```

---

## 3. Cypher Queries for the 5 Red Flag Patterns

### PAT-01: Oferente Unico

```cypher
// Mark all competitive processes with exactly one bidder
MATCH (p:Proceso)
WHERE p.tipo IN ['Licitacion Publica', 'Seleccion Abreviada', 'Concurso de Meritos']
  AND p.numero_oferentes IS NOT NULL
  AND toInteger(p.numero_oferentes) = 1
SET p.flag_oferente_unico = true,
    p.flag_computed_at = datetime()
RETURN count(p) AS flagged_count;

// Clear flags on processes that no longer qualify (rerunnable)
MATCH (p:Proceso)
WHERE NOT (p.tipo IN ['Licitacion Publica', 'Seleccion Abreviada', 'Concurso de Meritos']
           AND toInteger(coalesce(p.numero_oferentes, '0')) = 1)
SET p.flag_oferente_unico = false;
```

### PAT-02: Periodo de Licitacion Corto

```cypher
// Flag processes where publication-to-close window is under 5 days
MATCH (p:Proceso)
WHERE p.fecha_publicacion IS NOT NULL
  AND p.fecha_cierre IS NOT NULL
  AND duration.between(date(p.fecha_publicacion), date(p.fecha_cierre)).days < 5
SET p.flag_periodo_corto = true,
    p.flag_periodo_dias = duration.between(date(p.fecha_publicacion), date(p.fecha_cierre)).days,
    p.flag_computed_at = datetime()
RETURN count(p) AS flagged_count;
```

### PAT-03: Adicion al Valor del Contrato

```cypher
// Flag contracts where valor_final exceeds 120% of valor_inicial
// valor_contrato stores the final value; valor_adjudicado stores the original
// Threshold configurable: PCTG = 1.20 (20% over)
MATCH (c:Contrato)
WHERE c.valor_contrato IS NOT NULL
  AND c.valor_adjudicado IS NOT NULL
  AND c.valor_adjudicado > 0
  AND toFloat(c.valor_contrato) > toFloat(c.valor_adjudicado) * 1.20
SET c.flag_adicion_valor = true,
    c.flag_adicion_pct = round((toFloat(c.valor_contrato) / toFloat(c.valor_adjudicado) - 1) * 100, 1),
    c.flag_computed_at = datetime()
RETURN count(c) AS flagged_count;
```

### PAT-04: Concentracion de Contratacion Directa

```cypher
// For each (empresa, entidad) pair: compute share of direct-award contract value
// Flag empresa if it receives > 50% of a single entidad's direct-award total
// Rolling 12-month window
WITH date() - duration('P1Y') AS cutoff
MATCH (empresa:Empresa)-[:EJECUTA]->(c:Contrato)<-[:ADJUDICO]-(entidad:EntidadPublica)
WHERE c.modalidad = 'Contratacion Directa'
  AND c.fecha_firma IS NOT NULL
  AND date(c.fecha_firma) >= cutoff
WITH entidad, empresa, 
     sum(toFloat(c.valor_contrato)) AS empresa_total,
     collect(entidad.codigo_entidad) AS entidad_ids
WITH entidad, empresa, empresa_total, entidad_ids,
     [(entidad)-[:ADJUDICO]->(c2:Contrato)
      WHERE c2.modalidad = 'Contratacion Directa'
        AND date(c2.fecha_firma) >= date() - duration('P1Y')
      | toFloat(c2.valor_contrato)] AS all_values
WITH entidad, empresa, empresa_total,
     reduce(total = 0.0, v IN all_values | total + v) AS entidad_total
WHERE entidad_total > 0
  AND empresa_total / entidad_total > 0.50
SET empresa.flag_concentracion_directa = true,
    empresa.flag_computed_at = datetime()
WITH empresa, collect(entidad.codigo_entidad) AS flagging_entidades
SET empresa.flag_concentracion_entidades = flagging_entidades
RETURN count(DISTINCT empresa) AS flagged_count;
```

### PAT-05: Contratista Sancionado con Contrato Activo

```cypher
// Flag empresas/personas that have active sanctions AND active contracts
MATCH (e)-[:SANCIONO]->(s:Sancion)
WHERE e:Empresa OR e:Persona
MATCH (e)-[:EJECUTA]->(c:Contrato)
WHERE c.fecha_fin IS NOT NULL
  AND date(c.fecha_fin) >= date()
SET e.flag_contratista_sancionado = true,
    e.flag_computed_at = datetime()
RETURN count(DISTINCT e) AS flagged_count;

// Clear flag for entities that no longer have active contracts + sanctions
MATCH (e)
WHERE (e:Empresa OR e:Persona)
  AND e.flag_contratista_sancionado = true
  AND NOT (
    (e)-[:SANCIONO]->(:Sancion)
    AND (e)-[:EJECUTA]->(:Contrato {flag_active: true})
  )
SET e.flag_contratista_sancionado = false;
```

### Batch Detector Runner

```python
# etl/pattern_detection/detector.py
import asyncio
from neo4j import AsyncGraphDatabase

QUERIES = {
    "pat01": """
        MATCH (p:Proceso)
        WHERE p.tipo IN ['Licitacion Publica', 'Seleccion Abreviada', 'Concurso de Meritos']
          AND toInteger(coalesce(p.numero_oferentes, '999')) = 1
        SET p.flag_oferente_unico = true, p.flag_computed_at = datetime()
        RETURN count(p) AS flagged
    """,
    # ... remaining queries
}

class PatternDetector:
    def __init__(self, neo4j_uri: str, user: str, password: str):
        self.driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(user, password))

    async def run_all(self) -> dict[str, int]:
        results = {}
        async with self.driver.session() as session:
            for name, query in QUERIES.items():
                record = await session.run(query)
                summary = await record.consume()
                results[name] = summary.counters.properties_set
        return results

    async def close(self):
        await self.driver.close()
```

---

## 4. Vite + React Project Scaffolding

### Scaffold Command

```bash
# From project root
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

The existing `frontend/Dockerfile` (node:20-alpine builder → nginx:1.27-alpine) and `frontend/nginx.conf` already match the expected output: `dist/` served statically, `/api/` proxied to `api:8000`. No changes needed to infra.

### Tailwind CSS 4 Setup with Vite

Tailwind 4 uses a Vite plugin (not PostCSS-based):

```bash
npm install -D tailwindcss @tailwindcss/vite
```

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',  // Dev proxy for local FastAPI
    },
  },
})
```

```css
/* src/index.css */
@import "tailwindcss";
```

No `tailwind.config.js` needed with Tailwind 4 — configuration is in CSS.

### TypeScript Config (tsconfig.json)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

### package.json Scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "type-check": "tsc --noEmit"
  }
}
```

---

## 5. Tailwind CSS for Spanish UI

### Design Token Decisions (YOLO Mode)

For a Colombian investigative journalism platform, the aesthetic should be:
- Professional, data-dense, high-trust
- **Dark header / white content area** — newspaper digital aesthetic
- Primary: slate-900 header, white main, slate-50 alternating rows
- Accent: amber-500 (flags, warnings) — evokes urgency without alarm
- Danger: red-500 (sanctions, critical flags)
- Success: green-600 (data fresh, no flags)
- Body font: system-ui (no external font dependency, fast load)
- Mono font: for NIT/cedula display

### Key UI Patterns

**Search bar (BuscarPage):**
```html
<div class="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4">
  <h1 class="text-3xl font-bold text-slate-900 mb-2">HunterLeech</h1>
  <p class="text-slate-500 mb-8 text-sm">Plataforma anticorrupcion — contratacion publica colombiana</p>
  <input
    class="w-full max-w-2xl px-4 py-3 text-lg border border-slate-300 rounded-lg shadow-sm
           focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
    placeholder="Buscar por NIT, cedula o nombre..."
  />
</div>
```

**Red flag badge:**
```html
<!-- "oferente_unico" flag -->
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium
             bg-amber-100 text-amber-800 border border-amber-200">
  ⚠ Oferente Unico
</span>

<!-- "contratista_sancionado" flag — red -->
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium
             bg-red-100 text-red-800 border border-red-200">
  ⛔ Contratista Sancionado
</span>
```

**Provenance block:**
```html
<div class="text-xs text-slate-400 border-t border-slate-100 pt-2 mt-4">
  Fuente: <span class="font-mono">rpmr-utcd</span> (SECOP Integrado) · 
  Actualizado: <time>2026-04-01</time>
</div>
```

**Contract value formatting (Colombian COP):**
```typescript
const formatCOP = (value: number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
// → "$1.234.567.890"
```

---

## 6. Sigma.js Performance Considerations

### Node Limit Guidance

- < 500 nodes: No special handling needed; default renderer is fast
- 500–5,000 nodes: Disable edge labels; use `reducers` to hide low-degree nodes by default
- 5,000+ nodes: Enable WebGL node program; use `PartialGraph` to render only the ego network (depth=2 cap already enforced by API)

### Interaction Patterns

```typescript
// useRegisterEvents for click + hover
const registerEvents = useRegisterEvents();

registerEvents({
  clickNode: ({ node }) => {
    navigate(`/perfil/${node}`);
  },
  enterNode: ({ node }) => {
    // highlight node neighborhood
    setSidebar({ open: true, nodeId: node });
  },
  leaveNode: () => {
    setSidebar(prev => ({ ...prev, open: false }));
  },
});
```

### Sigma Settings for Procurement Graphs

```typescript
<SigmaContainer
  settings={{
    renderEdgeLabels: false,        // Too noisy at scale; show on hover only
    defaultEdgeColor: "#CBD5E1",    // slate-300
    defaultNodeColor: "#3B82F6",    // blue-500 default, overridden per node
    labelThreshold: 6,              // Only render labels for nodes with size >= 6
    minCameraRatio: 0.1,
    maxCameraRatio: 10,
    allowInvalidContainer: false,
  }}
/>
```

---

## 7. Pattern Detection Integration with ETL

### When to Run

Pattern detection runs AFTER data ingestion, before API queries. It is a batch job:

```
ETL pipelines (nightly)
  └─> Neo4j updated with fresh contracts/processes
  └─> python -m etl.pattern_detection.run_flags
      └─> Sets flag_* properties on nodes
  └─> FastAPI reads flags as node properties in entity/contract responses
  └─> Frontend displays badges
```

### APScheduler Integration

The existing ETL scheduling via APScheduler (per STACK.md) should add pattern detection as a post-ETL job:

```python
# In the scheduler setup (api/scheduler.py or etl/run.py)
scheduler.add_job(
    run_all_pipelines,
    trigger=CronTrigger(hour=2, minute=0),  # 2:00 AM Colombia time
    id="etl_ingest",
)
scheduler.add_job(
    run_pattern_detection,
    trigger=CronTrigger(hour=4, minute=0),  # After ETL completes
    id="pattern_detection",
)
```

### Cypher WRITE Strategy

- All flag queries use `SET` (not `MERGE`) — flags are computed properties, not new nodes
- Each query is idempotent: running twice produces the same result
- `flag_computed_at` timestamp on every flagged node enables freshness tracking
- Clearing stale flags (entities no longer qualifying): explicit `SET flag = false` queries run before each detection pass

---

## 8. API Response Types (TypeScript)

```typescript
// types/entities.ts
export interface EntitySummary {
  id: string;
  type: "Empresa" | "Persona" | "EntidadPublica";
  nombre: string;
  nit?: string;
  cedula?: string;
  flags: RedFlagName[];
  fuente: string;
  ultima_actualizacion: string; // ISO8601
}

export interface ContractorProfile extends EntitySummary {
  contratos: ContractSummary[];
  sanciones: SancionSummary[];
  entidades_relacionadas: EntitySummary[];
}

// types/flags.ts
export type RedFlagName =
  | "flag_oferente_unico"
  | "flag_periodo_corto"
  | "flag_adicion_valor"
  | "flag_concentracion_directa"
  | "flag_contratista_sancionado";

export interface RedFlag {
  name: RedFlagName;
  label: string;       // Spanish display label
  description: string; // Spanish tooltip text
  severity: "warning" | "danger";
}

export const RED_FLAG_METADATA: Record<RedFlagName, RedFlag> = {
  flag_oferente_unico: {
    name: "flag_oferente_unico",
    label: "Oferente Unico",
    description: "Solo se recibio una oferta en este proceso competitivo",
    severity: "warning",
  },
  flag_periodo_corto: {
    name: "flag_periodo_corto",
    label: "Licitacion Corta",
    description: "El periodo de publicacion del proceso fue inferior a 5 dias",
    severity: "warning",
  },
  flag_adicion_valor: {
    name: "flag_adicion_valor",
    label: "Adicion de Valor",
    description: "El valor final del contrato supera en mas del 20% el valor adjudicado",
    severity: "warning",
  },
  flag_concentracion_directa: {
    name: "flag_concentracion_directa",
    label: "Concentracion Directa",
    description: "Este contratista recibe mas del 50% de las adjudicaciones directas de una entidad",
    severity: "warning",
  },
  flag_contratista_sancionado: {
    name: "flag_contratista_sancionado",
    label: "Contratista Sancionado",
    description: "Este contratista tiene sanciones activas y contratos en ejecucion",
    severity: "danger",
  },
};
```

---

## Key Findings and Decisions

| Finding | Decision |
|---------|----------|
| Sigma.js requires graphology as its graph model — they are tightly coupled | Install both; do not try to use another graph model with Sigma |
| Tailwind 4 uses a Vite plugin, not PostCSS | Use `@tailwindcss/vite` plugin; do not add `tailwind.config.js` |
| React Router 6 has `createBrowserRouter` as preferred API (not `<BrowserRouter>`) | Use `createBrowserRouter` for data loader compatibility in v2 |
| TanStack Query `staleTime` should match ETL cadence | Set `staleTime: 5 * 60 * 1000` (5 min) — data changes nightly, not in real-time |
| Pattern detection Cypher queries use `SET` on existing nodes (not `MERGE`) | No new node labels needed; flags are properties on existing nodes |
| ForceAtlas2 layout needs 100+ iterations for meaningful layout on sparse graphs | Run layout client-side after graph loads; ForceAtlas2 is fast at depth=2 scale |
| nginx.conf and Dockerfile already correct for Vite SPA | No infra changes needed in Phase 4; scaffold drops into existing `frontend/` directory |
| Colombian COP formatting uses `es-CO` locale | `Intl.NumberFormat("es-CO", { style: "currency", currency: "COP" })` |

---

*Research completed: 2026-04-09*  
*Sources: @react-sigma/core docs, graphology docs, Sigma.js v3 README, Tailwind CSS v4 docs, TanStack Query v5 docs, React Router v6 docs, Open Contracting Partnership red flags guide, Neo4j Cypher manual*
