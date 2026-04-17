# Feature Landscape

**Domain:** Anticorruption / Public Procurement Transparency Platform
**Project:** HunterLeech (Colombia)
**Researched:** 2026-04-09
**Overall confidence:** HIGH (cross-referenced against br/acc, PACO, ProACT, OCCRP Aleph, Open Contracting Partnership)

---

## Table Stakes

Features users (journalists, veedurias, ONGs) expect. Missing any of these and the platform is not useful enough to open.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Entity search by identifier** | Users arrive with a NIT, cedula, or name. If they can't look it up immediately, they leave. PACO has this. | Low | Search by NIT (empresa), cedula (persona), nombre. Fuzzy matching critical because Colombian data has typos/variants. |
| **Contractor profile page** | Shows all contracts, sanctions, and related entities for a single contractor. PACO has this. Core unit of the tool. | Medium | Must aggregate across SECOP I+II, SIRI sanctions, RUES data. Single unified view. |
| **Contract detail view** | Journalists need to see the raw contract data — value, entity, timeline, process type, number of bidders. | Low | Display SECOP fields: valor contrato, entidad, modalidad, plazo, numero oferentes. |
| **Sanctions / fiscal responsibility flags** | A contractor with SIRI or Contraloria records must surface that prominently. Missing = platform is dangerous (may send users to sanctioned contractors). | Low-Medium | Pull from SIRI (Procuraduria) and Boletin Responsables Fiscales (Contraloria). |
| **Automated data ingestion** | Data must stay current. Stale data erodes trust immediately. | Medium | Socrata SODA API polling for SECOP, SIGEP, SIRI. Incremental updates, not full reloads. |
| **Per-source data freshness indicator** | Users need to know "this data was last updated on X." Trust depends on it. | Low | Timestamp per source in UI header and API responses. |
| **Privacy-safe defaults** | Ley 1581/2012 (habeas data) compliance is non-negotiable for a Colombian public deployment. Exposing protected personal data creates legal liability. | Medium | No direct personal data beyond what's in public government records. Role-based exposure for sensitive fields. |
| **Spanish-language interface** | Target users are Colombian. English UI creates adoption friction. | Low | All labels, errors, help text in Spanish. |
| **Reproducible local deployment** | Journalists and ONGs in Colombia may distrust cloud-hosted tools. br/acc established Docker Compose as the reference pattern. | Low-Medium | Docker Compose for full stack. One-command startup. |

---

## Differentiators

Features that go beyond what PACO and existing tools offer. These are the reason HunterLeech exists.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Graph relationship visualization** | PACO shows lists. HunterLeech shows networks. A journalist can see that Empresa X shares a legal representative with Empresa Y which shares a board member with Empresa Z, all awarded contracts by the same entidad. This is the core insight. | High | Neo4j backend + react-force-graph or d3-force frontend. Interactive, zoomable, filterable. Requires solid entity resolution first. |
| **Cross-source entity linking** | The same natural person (by cedula) appears as representante legal in RUES, as servidor publico in SIGEP, and has sanctions in SIRI. Linking these is invisible in PACO. | High | Entity resolution across sources. Cedula as primary key for persons, NIT for companies. Requires careful deduplication — Colombian data has formatting inconsistencies. |
| **Red flag / pattern detection** | Automatically flag contracts exhibiting known risk patterns. Reduces analyst time from hours to minutes. | High | See "Implemented Red Flags" table below. Start with 5-8 high-value indicators; do not boil the ocean. |
| **Public REST API** | br/acc has this. PACO does not. Allows investigative teams, academia, and other tools to query the graph programmatically. Multiplies impact. | Medium | FastAPI endpoints. Rate-limited. OpenAPI docs auto-generated. Read-only. |
| **Per-source audit trail** | Every data point shows its origin: dataset ID, ingestion timestamp, source URL. br/acc implements this. Lets journalists cite their source exactly. | Medium | Store provenance metadata in Neo4j node/relationship properties. Surface in UI and API response. |
| **Cypher / graph query access** | Advanced users (data journalists, researchers) can run custom graph traversals. Unique capability vs PACO's fixed query UI. | Medium | Read-only Cypher endpoint or query builder. Rate-limited. Needs access control. |
| **Concentration analysis** | How much of an entidad's contracting goes to a single contratista? Automated ranking surfaces monopolistic patterns that are invisible in contract-by-contract browsing. | Medium | Aggregate query on graph. Configurable time window. Display as table + chart. |
| **Newly-created company flag** | Company registered within N days of contract award is a classic fraud pattern. Requires joining RUES (fecha constitucion) with SECOP (fecha firma). | Medium | Requires RUES data integration. Flag on contractor profile and in red flags engine. |
| **Conflict of interest detection** | Public servant in SIGEP who is also representante legal or socio of a contractor. | High | Requires cross-linking SIGEP persons with RUES company roles by cedula. Privacy-sensitive: show role, not personal details beyond what's public. |

---

### Implemented Red Flags (for Pattern Detection Feature)

Sourced from Open Contracting Partnership's 73-indicator taxonomy, filtered to what SECOP data supports.

| Red Flag | Indicator | Data Required | Priority |
|----------|-----------|---------------|----------|
| Single bidder | Only one offer received for a competitive process | SECOP numero_oferentes | P0 |
| Short tender period | Tender window below sector threshold (e.g., < 5 days) | SECOP fecha_publicacion, fecha_cierre | P0 |
| Contract value amendment | Final value > N% above awarded value | SECOP valor_contrato vs addendas | P0 |
| Direct award concentration | Contratista receives > X% of direct awards from same entidad | SECOP modalidad_contratacion | P0 |
| Newly created company | Company registered < 180 days before contract award | RUES fecha_matricula + SECOP fecha_firma | P1 |
| Sanctioned contractor | Active contract with contractor having SIRI/Contraloria sanction | SIRI + SECOP join on NIT | P0 |
| Contract value vs market | Benford's law deviation in contract values for a buyer | SECOP valor_contrato | P2 |
| Mass contract concentration | Single contractor receives > Y% of entity budget | SECOP aggregation | P1 |

---

## Anti-Features

Features to explicitly NOT build in v1, and why.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Guilt scores / corruption ranking** | The platform's legal and ethical position is to surface connections, not render verdicts. A "corruption score" invites defamation claims, discourages use by cautious institutions, and is methodologically indefensible with available data. PACO explicitly avoids this. br/acc explicitly avoids this. Harvard research confirms "transparency alone backfires." | Show raw indicators and let users interpret. Label flags as "riesgo potencial," not "corrupto." |
| **Scraped data without API** | Scraping portales without API creates legal ambiguity, fragility (structure changes break ingestion), and maintenance burden. PROJECT.md out-of-scope. | Socrata API only for v1. Document sources without API as "future." |
| **Personal data beyond public record** | DIAN RUT, judicial antecedentes, addresses — protected under Ley 1581. Using them without authorization exposes the project to habeas data complaints. | Use only what government publishes in open datasets. Don't integrate Verifik/Apitude APIs in v1. |
| **Crowdsourced / user-submitted data** | User reports, tips, manual entries — require moderation, legal review, identity verification, potential defamation exposure. Massive scope expansion for v1. | Focus on official government data only. A "report a tip" feature is a v3 concern. |
| **Real-time streaming alerts / push notifications** | Complex infrastructure (websockets, notification service, user accounts). Low return for MVP. Journalists pull, they don't wait for push. | Export to CSV/JSON for offline analysis. API polling is sufficient for v1. |
| **Mobile application** | PROJECT.md explicitly out of scope. Native mobile doubles frontend effort for marginal gain in this user segment (desktop-heavy journalists). | Responsive web works. Don't build native. |
| **Fine-grained access controls / user accounts** | RBAC, login, org management — large surface area, significant auth complexity. Public data should be publicly accessible. | Make everything public-read. If private deployment is needed, use network-level controls (VPN, Docker network). |
| **Document management / upload** | OCCRP Aleph does this. HunterLeech is a graph/data platform, not a document store. Storing PDFs, contracts as files is scope creep. | Link to source URLs for documents. Let Aleph handle document analysis. |
| **ML-based entity resolution** | Tempting but high engineering cost, unpredictable quality, hard to audit, and Colombian data has consistent identifiers (cedula, NIT) that make deterministic matching viable. | Use deterministic matching on cedula/NIT as primary key. Fuzzy name matching as fallback only when identifier is missing. |
| **International data sources in v1** | OFAC sanctions, EU lists — br/acc integrates these, but Colombian use case is domestic. Adding international scope in v1 dilutes focus and complicates legal/privacy analysis. | Design schema to accommodate international nodes; leave ingestion for v2+. |

---

## Feature Dependencies

```
Automated ingestion (SECOP, SIGEP, SIRI)
  └─> Entity search by identifier
  └─> Contract detail view
  └─> Sanctions flags (SIRI data)
  └─> Per-source audit trail

Entity search + Contract data
  └─> Contractor profile page

Contractor profile page
  └─> Graph relationship visualization  (needs multiple entities linked)
  └─> Red flag: Single bidder
  └─> Red flag: Short tender period
  └─> Red flag: Direct award concentration

RUES integration (company registry)
  └─> Red flag: Newly created company
  └─> Cross-source entity linking (company roles)

SIGEP integration (public servants)
  └─> Cross-source entity linking (person roles)
  └─> Conflict of interest detection

Cross-source entity linking
  └─> Graph relationship visualization (meaningful graph)
  └─> Conflict of interest detection
  └─> Concentration analysis

Red flag / pattern detection
  └─> Requires: automated ingestion + entity linking + at least SECOP + SIRI

Public REST API
  └─> Requires: all ingestion + entity model stable
  └─> Graph query access (Cypher)
```

---

## MVP Recommendation

Phase 1 target — everything needed to be useful enough that a journalist publishes a story using it.

**Must ship:**
1. Automated SECOP ingestion (contratos, procesos, sanciones) via Socrata
2. Automated SIRI ingestion (sanciones Procuraduria) via Socrata
3. Entity search (by NIT, cedula, nombre) with fuzzy fallback
4. Contractor profile page (contracts, sanctions, related entities)
5. Contract detail view
6. Sanctions flag on contractor profile (SIRI + Contraloria)
7. Per-source data freshness indicator
8. Privacy-safe defaults (Ley 1581)
9. Spanish UI
10. Docker Compose local deployment

**Defer to Phase 2:**
- Graph visualization (needs entity resolution to be meaningful)
- Cross-source entity linking (SIGEP + RUES joins)
- Red flag engine (single bidder, short tender period, direct award concentration)
- Public REST API (ship after data model is stable)

**Defer to Phase 3+:**
- Conflict of interest detection (requires SIGEP + RUES both integrated)
- Newly-created company flag (requires RUES integration)
- Cypher query access
- Concentration analysis dashboards

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Table stakes | HIGH | Cross-validated against PACO (Colombian reference), br/acc (direct reference), OCCRP Aleph (journalism benchmark) |
| Red flag indicators | HIGH | Open Contracting Partnership publishes 73-indicator taxonomy; Colombia-specific validation from 2019 OCP Latin America study |
| Differentiators | HIGH | br/acc features confirmed via GitHub; ProACT confirmed via World Bank blog; Aleph Pro roadmap confirmed via OCCRP announcement |
| Anti-features | MEDIUM | Based on civic tech failure literature (Harvard Ash Center), legal framework (Ley 1581), and reference project patterns. Some are judgment calls. |
| Feature dependencies | HIGH | Logical derivation from data model; confirmed by br/acc's ETL sequencing (45 pipelines build from core identifiers outward) |

---

## Sources

- [br/acc GitHub (World-Open-Graph)](https://github.com/World-Open-Graph/br-acc) — direct reference implementation
- [PACO Portal Anticorrupcion Colombia](https://portal.paco.gov.co/) — Colombian incumbent, contractor lookup
- [ProACT World Bank Platform](https://blogs.worldbank.org/en/governance/new-global-anticorruption-and-transparency-platform-proact-empowers-stakeholders-use) — risk indicators model
- [OCCRP Aleph Pro announcement](https://www.occrp.org/en/announcement/occrp-announces-a-new-chapter-for-its-investigative-data-platform-aleph-pro) — journalism platform benchmark
- [Open Contracting Partnership — Red Flags guide](https://www.open-contracting.org/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/) — 73 indicator taxonomy
- [OCP Latin America red flags study](https://www.open-contracting.org/2019/06/27/examining-procurement-red-flags-in-latin-america-with-data/) — Colombia-specific validation
- [Harvard Ash Center — Transparency is Insufficient](https://ash.harvard.edu/articles/transparency-is-insufficient-lessons-from-civic-technology-for-anticorruption/) — civic tech failure analysis
- [OpenSanctions / FollowTheMoney](https://github.com/opensanctions/followthemoney/) — entity data model reference
- [OCDS Standard](https://standard.open-contracting.org/) — Colombia publishes SECOP in this format
- [TransparenCEE Civic Tech Fails](https://techfails.transparencee.org/) — over-engineering failure cases
