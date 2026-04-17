# Requirements: HunterLeech

**Defined:** 2026-04-09
**Core Value:** Hacer visible las conexiones ocultas entre funcionarios publicos, empresas contratistas y recursos del Estado colombiano.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Infrastructure

- [x] **INFRA-01**: Sistema desplegable con un solo comando via Docker Compose (Neo4j + FastAPI + React)
- [x] **INFRA-02**: Esquema de grafos en Neo4j con constraints de unicidad para entidades (Persona, Empresa, EntidadPublica, Contrato, Proceso, Sancion)
- [x] **INFRA-03**: Estrategia de entity resolution documentada con reglas de normalizacion de NIT y cedula antes de cualquier carga de datos

### ETL / Ingesta de Datos

- [x] **ETL-01**: Pipeline automatizado de ingesta SECOP Integrado (rpmr-utcd) via Socrata SODA API con paginacion y App Token
- [x] **ETL-02**: Pipeline de ingesta SECOP II Contratos Electronicos (jbjy-vk9h)
- [x] **ETL-03**: Pipeline de ingesta SIGEP servidores publicos (2jzx-383z)
- [x] **ETL-04**: Pipeline de ingesta SIRI sanciones disciplinarias Procuraduria (iaeu-rcn6)
- [x] **ETL-05**: Pipeline de ingesta Multas y Sanciones SECOP (4n4q-k399)
- [x] **ETL-06**: Entity linking cross-source: vincular personas por cedula y empresas por NIT entre SECOP, SIGEP, SIRI
- [x] **ETL-07**: Metadata de proveniencia por registro: dataset ID, timestamp de ingesta, URL fuente
- [x] **ETL-08**: Ejecucion incremental (no recarga completa) con idempotencia via MERGE en Neo4j

### Backend / API

- [x] **API-01**: Endpoint de busqueda por NIT, cedula o nombre con fuzzy matching
- [x] **API-02**: Endpoint de perfil de contratista: contratos, sanciones, entidades relacionadas
- [x] **API-03**: Endpoint de detalle de contrato: valor, entidad, modalidad, plazo, oferentes
- [x] **API-04**: Endpoint de grafo de relaciones: nodos y aristas para un entity dado con profundidad configurable
- [x] **API-05**: Middleware de privacidad (PUBLIC_MODE): oculta campos sensibles segun Ley 1581/2012
- [x] **API-06**: Rate limiting y timeout en queries para proteger Neo4j
- [x] **API-07**: Indicador de frescura de datos por fuente en respuestas API

### Frontend

- [x] **UI-01**: Busqueda principal por NIT, cedula o nombre de entidad/contratista
- [x] **UI-02**: Pagina de perfil de contratista con contratos, sanciones y flags
- [x] **UI-03**: Vista de detalle de contrato con todos los campos SECOP
- [x] **UI-04**: Visualizacion interactiva de grafo de relaciones (Sigma.js/WebGL)
- [x] **UI-05**: Indicador de frescura de datos por fuente
- [x] **UI-06**: Proveniencia visible en cada dato mostrado (fuente, fecha)
- [x] **UI-07**: Interfaz completamente en espanol
- [x] **UI-08**: Responsive web (no app movil)

### Deteccion de Patrones

- [x] **PAT-01**: Flag de oferente unico: procesos competitivos con un solo oferente
- [x] **PAT-02**: Flag de periodo de licitacion corto: ventana inferior al umbral del sector
- [x] **PAT-03**: Flag de adicion al valor del contrato: valor final > N% sobre valor adjudicado
- [x] **PAT-04**: Flag de concentracion de contratacion directa: contratista con > X% de adjudicaciones directas de una entidad
- [x] **PAT-05**: Flag de contratista sancionado: contrato activo con contratista con sancion SIRI/Contraloria

### Compliance / Privacidad

- [x] **PRIV-01**: Clasificacion de campos por nivel de privacidad antes de almacenar cualquier dato
- [x] **PRIV-02**: PUBLIC_MODE desactiva exposicion de datos personales protegidos por Ley 1581/2012
- [x] **PRIV-03**: Toda relacion mostrada incluye fuente y significado semantico (no implicar culpabilidad)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Datos Adicionales

- **RUES-01**: Integracion con RUES para datos empresariales (requiere credenciales institucionales o API comercial)
- **CTRL-01**: Parseo del Boletin de Responsables Fiscales de la Contraloria (PDF)
- **INTL-01**: Listas de sanciones internacionales (OFAC, UE, ONU)

### Funcionalidades Avanzadas

- **PAT-06**: Flag de empresa recien creada (< 180 dias antes de adjudicacion) — requiere RUES
- **PAT-07**: Deteccion de conflicto de interes (servidor publico que es representante legal de contratista) — requiere SIGEP + RUES cross-link
- **PAT-08**: Analisis de Benford en valores de contrato por entidad
- **ADV-01**: Endpoint Cypher de solo lectura para consultas avanzadas
- **ADV-02**: Analisis de centralidad via Neo4j GDS (PageRank, Betweenness)
- **ADV-03**: Exportacion CSV/JSON de resultados de busqueda
- **ADV-04**: API publica documentada con OpenAPI para uso externo

## Out of Scope

| Feature | Reason |
|---------|--------|
| Scores de culpabilidad / ranking de corrupcion | Riesgo legal (difamacion), metodologicamente indefendible, todos los referentes lo evitan |
| Scraping de portales sin API | Fragilidad, ambiguedad legal, carga de mantenimiento |
| Datos personales protegidos (RUT, antecedentes judiciales) | Ley 1581/2012 habeas data |
| Datos crowdsourced / tips de usuarios | Requiere moderacion, verificacion, exposicion legal |
| Alertas push / notificaciones en tiempo real | Complejidad infraestructura vs valor en MVP |
| App movil nativa | Esfuerzo doble de frontend, usuarios son desktop-heavy |
| Cuentas de usuario / RBAC | Datos publicos deben ser publicamente accesibles |
| Gestion de documentos / upload | Fuera del scope de plataforma de grafos |
| Entity resolution con ML | Costoso, impredecible; matching deterministico por cedula/NIT es viable |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| PRIV-01 | Phase 1 | Complete |
| ETL-01 | Phase 1 | Complete |
| ETL-07 | Phase 1 | Complete |
| ETL-08 | Phase 1 | Complete |
| ETL-02 | Phase 2 | Complete |
| ETL-03 | Phase 2 | Complete |
| ETL-04 | Phase 2 | Complete |
| ETL-05 | Phase 2 | Complete |
| ETL-06 | Phase 2 | Complete |
| API-01 | Phase 3 | Complete |
| API-02 | Phase 3 | Complete |
| API-03 | Phase 3 | Complete |
| API-04 | Phase 3 | Complete |
| API-05 | Phase 3 | Complete |
| API-06 | Phase 3 | Complete |
| API-07 | Phase 3 | Complete |
| PRIV-02 | Phase 3 | Complete |
| PRIV-03 | Phase 3 | Complete |
| UI-01 | Phase 4 | Complete |
| UI-02 | Phase 4 | Complete |
| UI-03 | Phase 4 | Complete |
| UI-04 | Phase 4 | Complete |
| UI-05 | Phase 4 | Complete |
| UI-06 | Phase 4 | Complete |
| UI-07 | Phase 4 | Complete |
| UI-08 | Phase 4 | Complete |
| PAT-01 | Phase 4 | Complete |
| PAT-02 | Phase 4 | Complete |
| PAT-03 | Phase 4 | Complete |
| PAT-04 | Phase 4 | Complete |
| PAT-05 | Phase 4 | Complete |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0

---
*Requirements defined: 2026-04-09*
*Last updated: 2026-04-09 after roadmap creation*
