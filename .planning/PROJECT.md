# HunterLeech

## What This Is

Plataforma open-source de inteligencia anticorrupcion para Colombia. Agrega bases de datos publicas dispersas (SECOP, SIGEP, SIRI, RUES, Contraloria) en una base de datos de grafos unificada, permitiendo a periodistas, veedurias ciudadanas y ONGs detectar rapidamente patrones sospechosos en contratacion publica: redes de testaferros, contratos inflados, conflictos de interes y concentracion irregular de adjudicaciones.

Inspirado en [br/acc](https://github.com/brunoclz/br-acc) (Brasil), adaptado al ecosistema de datos abiertos colombiano.

## Core Value

Hacer visible las conexiones ocultas entre funcionarios publicos, empresas contratistas y recursos del Estado colombiano, para que cualquier ciudadano pueda identificar focos de corrupcion en la contratacion publica.

## Requirements

### Validated

- Ingesta automatizada de datos SECOP Integrado via API Socrata — Validated in Phase 1: Foundation
- Modelado de grafos con constraints de unicidad (Persona, Empresa, EntidadPublica, Contrato, Proceso, Sancion) — Validated in Phase 1: Foundation
- Privacidad por defecto: clasificacion de campos segun Ley 1581/2012 — Validated in Phase 1: Foundation
- Infraestructura Docker Compose reproducible (Neo4j + FastAPI + Nginx) — Validated in Phase 1: Foundation

### Active

- [ ] Ingesta automatizada de datos SECOP (contratos, procesos, sanciones) via API Socrata
- [ ] Ingesta de datos SIGEP (servidores publicos) via API Socrata
- [ ] Ingesta de sanciones SIRI (Procuraduria) via API Socrata
- [ ] Ingesta de datos empresariales RUES (cuando disponible)
- [ ] Ingesta del Boletin de Responsables Fiscales (Contraloria)
- [ ] Modelado de grafos: entidades (personas, empresas, instituciones) y relaciones (contratos, representacion legal, sanciones)
- [ ] Motor de deteccion de patrones sospechosos (contratos inflados, empresas recien creadas, concentracion de contratos)
- [ ] API REST publica para consultas programaticas
- [ ] Interfaz web con visualizacion de grafos interactiva
- [ ] Busqueda por NIT, cedula, nombre de entidad o contratista
- [ ] Privacidad por defecto: datos sensibles protegidos segun Ley 1581/2012 (habeas data)

### Out of Scope

- Acusaciones o calificaciones de culpabilidad — la plataforma presenta conexiones, no emite juicios
- Datos protegidos por habeas data (RUT individual, antecedentes judiciales personales) — requieren APIs comerciales de pago
- Scraping de portales sin API — MVP usa solo fuentes con acceso programatico libre
- App movil — v1 es web only

## Context

### Ecosistema de Datos Colombiano

**Fuentes con API abierta (Socrata/SODA en datos.gov.co):**

| Fuente | Dataset ID | Datos clave |
|--------|-----------|-------------|
| SECOP Integrado | `rpmr-utcd` | Contratos publicos unificados SECOP I+II |
| SECOP II Contratos | `jbjy-vk9h` | Contratos electronicos detallados |
| SECOP II Procesos | `p6dx-8zbt` | Procesos de contratacion |
| Multas/Sanciones SECOP | `4n4q-k399` | Sanciones a contratistas |
| SIRI Procuraduria | `iaeu-rcn6` | Sanciones disciplinarias |
| Servidores Publicos SIGEP | `2jzx-383z` | Directorio funcionarios |

Base URL: `https://www.datos.gov.co/resource/{ID}.json`
App Token gratuito recomendado. ~1,000 req/hora con token.

**Fuentes con acceso limitado:**
- RUES: API oficial requiere credenciales institucionales; alternativa comercial Verifik/Apitude
- Contraloria SIBOR: PDF trimestral sin API; parseable
- PACO Portal Anticorrupcion: descarga bulk + consulta por NIT

**Fuentes sin acceso programatico (futuro):**
- DIAN RUT, Procuraduria certificados, Policia antecedentes — requieren Apitude/Verifik (pago)

### Marco Legal
- Ley 1712/2014 (Transparencia y acceso a informacion publica)
- Ley 1581/2012 (Habeas data — proteccion datos personales)
- Art. 74 Constitucion (derecho de acceso a documentos publicos)
- OCDS (Open Contracting Data Standard) — Colombia publica en este formato

### Referencia
- br/acc (Brasil): Neo4j + FastAPI + React, 45 pipelines ETL, grafo de entidades publicas
- PACO (Colombia): Portal Anticorrupcion con 700M+ registros, pero sin API publica robusta

## Constraints

- **Stack**: Neo4j (grafos) + FastAPI (backend) + React (frontend) — alineado con br/acc para reusar patrones
- **Datos**: Solo fuentes publicas gratuitas en v1 (Socrata API)
- **Legal**: Cumplimiento Ley 1581/2012 — no exponer datos personales protegidos
- **Infraestructura**: Docker Compose para deployment local reproducible
- **Idioma**: Interfaz en espanol

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Neo4j como base de datos | Relaciones entre entidades son el core del producto; grafos son naturales para detectar redes | — Pending |
| FastAPI + Python | Ecosistema rico para ETL (pandas, httpx), alineado con br/acc | — Pending |
| React + TypeScript frontend | Librerias maduras de visualizacion de grafos (d3, react-force-graph) | — Pending |
| Solo Socrata API en v1 | Acceso gratuito, sin friccion legal, suficiente para MVP | — Pending |
| Privacidad por defecto | Alineado con Ley 1581/2012; instancias publicas no muestran datos sensibles | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-10 after Phase 1: Foundation completion*
