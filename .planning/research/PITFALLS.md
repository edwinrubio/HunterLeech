# Domain Pitfalls: Graph-Based Anticorruption Platform (HunterLeech)

**Domain:** Public procurement transparency / anticorruption civic tech / graph-based government data
**Researched:** 2026-04-09
**Sources:** Neo4j community docs, ICIJ offshore leaks methodology, Open Contracting Partnership quality guide, Harvard Ash Center civic tech research, br-acc project documentation, Colombian SECOP system analysis

---

## Critical Pitfalls

Mistakes in this category cause rewrites, legal exposure, or permanently corrupt the graph.

---

### Pitfall 1: Entity Resolution Treated as an Afterthought

**What goes wrong:** The pipeline ingests millions of SECOP records and creates one Neo4j node per raw row. The same contractor appears as 50 separate nodes: "CONSTRUCCIONES ALVAREZ SAS", "CONSTRUCCIONES ÁLVAREZ S.A.S.", "CONST ALVAREZ SAS", and variants with leading zeros dropped from the NIT. Analysts querying the graph see fragmented data; corruption patterns become invisible because the network is shredded into isolated islands.

**Why it happens:** Entity resolution feels like a data cleaning step you "come back to later." In practice, once millions of nodes exist in the graph with relationships attached, retroactive merging is extremely expensive—and wrong merges propagate errors transitively through the graph.

**Consequences:**
- Duplicate contractor nodes mean relationship counts are split, making concentration-of-contracts detection unreliable
- Graph traversals (find all contracts of person X) return incomplete results
- False negatives in corruption detection: a sanctioned contractor's contracts are invisible because sanctions are linked to a different name variant
- Retroactive deduplication requires touching every relationship in the graph

**Warning signs:**
- COUNT(DISTINCT nit) differs significantly from COUNT(DISTINCT nombre_contratista)
- Sample queries for a known company return fewer contracts than the raw SECOP web portal shows
- NIT field contains values like "0", "", "N/A", or non-numeric strings in a significant fraction of rows

**Prevention:**
- Define a canonical entity resolution strategy before writing any MERGE statements
- Use NIT as primary key for legal entities and cedula for natural persons — but normalize first: strip leading zeros, remove hyphens and spaces, handle null/empty as a special sentinel rather than merging all nulls into one node
- For name-only matching (where NIT is missing), use Splink (UK Ministry of Justice's open-source probabilistic record linkage library) to generate candidate pairs before inserting into Neo4j
- Implement a "raw record" layer separate from the "resolved entity" layer in the graph model: raw nodes store source data as-is; resolved nodes are created only after deduplication
- Flag unresolvable ambiguity explicitly rather than silently dropping or merging

**Phase to address:** Phase 1 (Data ingestion / ETL foundation). Must be solved before any graph population begins.

---

### Pitfall 2: SECOP I and SECOP II Treated as the Same Schema

**What goes wrong:** SECOP I (pre-2015, analog processes registered digitally) and SECOP II (fully electronic contracting) have fundamentally different schemas, field names, identifier formats, and data semantics. A pipeline written against SECOP II's `jbjy-vk9h` dataset will silently fail or produce wrong results when applied to SECOP I data. The "SECOP Integrado" dataset (`rpmr-utcd`) appears unified but inherits the inconsistencies of both systems.

**Why it happens:** The datasets have overlapping column names but different semantics. SECOP I recorded contracting stages as sequential documents; SECOP II records them as stateful process objects. Entity identifiers for the same contractor may differ between the two systems.

**Consequences:**
- Duplicate contracts in the graph (same contract from both SECOP I and SECOP Integrado)
- Broken joins between process-level and contract-level data
- Relationship counts inflated or deflated depending on which dataset is queried
- Colombia Compra Eficiente documented that system incidents affecting SECOP increased from 4,552 in 2022 to 17,787 in 2023, partly due to interoperability deficiencies between the two systems

**Warning signs:**
- Contract value distributions look bimodal with no obvious explanation
- The same contrato_id appears in both SECOP I and SECOP II rows with different amounts
- Contratista NIT format differs between datasets (with/without check digit, with/without hyphens)

**Prevention:**
- Write separate ETL pipelines for each source dataset; do not share transformation logic between SECOP I and SECOP II
- Use the dataset ID as a required provenance property on every raw node: `{fuente: "rpmr-utcd", row_id: "..."}`
- Add a deduplication step specifically for cross-SECOP duplicates, keyed on a composite of NIT + numero_contrato + entidad_nit
- Consult the official "Manual para el uso de Datos Abiertos del SECOP" (Colombia Compra Eficiente, 2024) before mapping any field

**Phase to address:** Phase 1 (schema design and ETL architecture). Schema decisions made here are expensive to reverse.

---

### Pitfall 3: Super Nodes Destroy Query Performance at Scale

**What goes wrong:** The graph model creates a single `:Municipality` node for Bogota, a single `:Sector` node for "Salud", or a single `:TipoContrato` node for "Prestación de Servicios". With millions of contracts, these categorical nodes acquire 500,000+ relationships. Any traversal that touches them — even tangentially — triggers a full relationship scan. Queries that ran in milliseconds on a sample dataset take hours in production.

**Why it happens:** Graph modelers coming from relational databases naturally normalize categorical values into reference tables (nodes). In Neo4j, low-cardinality categories connected to millions of records are super nodes — a recognized anti-pattern. SECOP data has extreme cardinality mismatches: ~1,100 municipalities, ~20 sectors, ~30 contract types, but millions of contracts.

**Consequences:**
- Queries involving any geographic or categorical filter become unusable
- MERGE on super nodes during ingestion causes write locks that serialize the entire pipeline
- Graph visualization tools try to render 500K relationships and crash the browser
- Pattern detection algorithms (shortest path, community detection) incorrectly treat everything as "close" to everything else, producing meaningless results

**Warning signs:**
- Any node where `SIZE((n)--())` exceeds ~50,000
- Ingestion pipeline slows progressively as data grows rather than staying constant
- Graph visualization shows a "hairball" centered on a few nodes

**Prevention:**
- Store categorical values as properties on contract nodes, not as separate nodes: `{municipio: "Bogota", departamento: "Cundinamarca"}` rather than `(:Contract)-[:IN]->(:Municipality {name: "Bogota"})`
- If geographic hierarchy is needed for traversal, create it as a small standalone hierarchy graph (1,122 municipalities → 33 departments → 1 country) and only connect it via indexed lookups, not direct relationships to contract nodes
- Create separate relationship types for different semantic roles: `-[:AWARDED_TO]->` for contractors, `-[:ISSUED_BY]->` for entities; never use a generic `-[:RELATES_TO]->`
- Run `MATCH (n) RETURN labels(n), count(*), avg(size((n)--()))` monthly during development and set a hard limit alert at 10,000 relationships per node

**Phase to address:** Phase 1 (graph model design). Must be explicit before any data is loaded. Adding a super node check to the CI test suite in Phase 2 prevents regressions.

---

### Pitfall 4: Displaying Connections as Implied Guilt — Legal and Reputational Risk

**What goes wrong:** The platform surfaces a network showing Person A connected to Company B connected to Sanctioned Entity C. A journalist publishes "Person A linked to corruption" based on the graph. Person A sues — or worse, is a common name (e.g., "Carlos Rodriguez") shared by thousands of Colombians, and the platform has conflated them.

**Why it happens:** Graph visualizations are inherently suggestive. A path between two nodes looks like evidence even when it is not. Automated "suspicious pattern" scoring amplifies this by assigning a number that journalists treat as a verdict. The ICIJ explicitly warns in its Offshore Leaks database: "Records come from leaked documents — there may be duplicates. Confirm the identity of any individual based on additional identifying information."

**Consequences:**
- Legal liability under Colombian defamation law (injuria, calumnia — Ley 599/2000 Arts. 220-228)
- SIC (Superintendencia de Industria y Comercio) complaints under Ley 1581/2012 for exposing personal data in a misleading context
- Platform shutdown or forced data takedown orders
- Erosion of trust from journalists and civil society if false accusations circulate

**Warning signs:**
- UI shows paths between entities without explaining what each relationship means
- "Risk scores" or "suspicious scores" appear in the interface without a clear methodology disclosure
- Person search returns results without disambiguation (multiple Carlos Rodriguez merged into one node)
- No mechanism for an affected person to flag incorrect data

**Prevention:**
- Every relationship in the UI must display its source, date, and semantic meaning: "Firmó contrato 12345 con entidad X en 2022 (fuente: SECOP II)"
- Never display aggregate "suspicion scores" — display raw facts and let users draw conclusions (consistent with br-acc's design philosophy)
- For natural persons (cedula-identified), require at minimum name + cedula match before displaying; warn prominently when only name was matched
- Add a visible "Reportar error" mechanism that generates a GitHub issue or sends an email to maintainers
- Display source provenance on every data point with a link to the original SECOP record
- Terms of use must explicitly state the platform presents public data connections, not accusations or legal determinations

**Phase to address:** Phase 2 (graph model) and Phase 4 (frontend). Legal disclaimer and provenance UI are required before any public deployment.

---

## Moderate Pitfalls

---

### Pitfall 5: Socrata Offset Pagination Produces Silent Gaps

**What goes wrong:** The ingestion pipeline uses `$offset` + `$limit` to paginate through millions of SECOP records. Between two pagination requests, a new record is inserted upstream (SECOP updates daily). The offset shifts, causing one record to be skipped silently. Over millions of records, thousands of contracts are missing from the graph.

**Why it happens:** Offset-based pagination is order-dependent. If the underlying dataset is sorted by insertion order and new records arrive during the crawl, offset indices shift. The SODA API returns no error — it simply returns the "next" page starting from the new offset.

**Warning signs:**
- Row count in Neo4j is consistently 0.5-2% lower than the dataset row count reported on datos.gov.co
- Running the pipeline twice produces different counts

**Prevention:**
- Sort all Socrata queries by a stable, immutable field: `$order=fecha_de_firma ASC` or use a unique record identifier
- After initial load, use the Socrata `$where=fecha_de_cargue > '{last_run_timestamp}'` filter for incremental updates instead of re-paginating the full dataset
- Implement a post-load count reconciliation step: compare `COUNT(*)` from the API metadata endpoint against nodes in Neo4j; alert if delta exceeds 0.1%
- Store the API response `X-SODA2-Fields` header and dataset `rowsUpdatedAt` timestamp with each run

**Phase to address:** Phase 1 (ETL pipeline design).

---

### Pitfall 6: Missing Indexes Before MERGE Causes Exponential Slowdown

**What goes wrong:** The pipeline runs MERGE statements to upsert nodes (create if not exists, match if exists). Without a unique constraint on the merge key, Neo4j performs a full label scan for every MERGE. At 100 nodes this is invisible; at 1 million nodes, a pipeline that should run in 20 minutes takes 48 hours.

**Why it happens:** Neo4j's MERGE does not automatically use an index — it requires an explicit unique constraint or index on the property used in the MERGE predicate. This is not obvious to developers coming from SQL (where primary keys are always indexed) or document databases.

**Warning signs:**
- Ingestion time grows super-linearly as the database fills
- `EXPLAIN MERGE (n:Empresa {nit: $nit})` shows "NodeByLabelScan" rather than "NodeIndexSeek"
- `PROFILE` output shows high `db hits` counts

**Prevention:**
- Create all constraints and indexes as the very first migration, before any data is loaded:
  ```cypher
  CREATE CONSTRAINT empresa_nit IF NOT EXISTS FOR (e:Empresa) REQUIRE e.nit IS UNIQUE;
  CREATE CONSTRAINT persona_cedula IF NOT EXISTS FOR (p:Persona) REQUIRE p.cedula IS UNIQUE;
  CREATE CONSTRAINT contrato_id IF NOT EXISTS FOR (c:Contrato) REQUIRE c.id_contrato IS UNIQUE;
  ```
- Add an index check to the ETL startup script: abort if required indexes are not present
- Use `apoc.periodic.iterate` with `batchSize: 1000` for bulk MERGEs; never run a single transaction over 10,000 rows

**Phase to address:** Phase 1 (infrastructure setup). Add a migration-runner that enforces index creation order.

---

### Pitfall 7: Ley 1581/2012 Scope Misunderstood — Public Role Data vs. Private Data

**What goes wrong:** The team interprets Ley 1581/2012 (habeas data) as prohibiting all display of personal information. The platform over-restricts and hides data that is legally public (e.g., a public servant's name and position, a contractor's NIT). Alternatively — and more dangerously — the team assumes all SECOP data is public and exposes home addresses, personal phone numbers, or cedulas of private citizens who appear as minor contractors or signatories.

**Why it happens:** Ley 1581/2012 creates a category of "datos semiprivados" and "datos privados" that overlap with public records in non-obvious ways. The law exempts data related to public functions of public servants but does not fully exempt all data in public contracting databases. SECOP records sometimes contain fields that were never meant to be personal-data-searchable (e.g., personal email of a technical supervisor on a contract).

**Consequences:**
- SIC investigation and fines for unauthorized personal data treatment
- Forced platform shutdown
- Conversely: overly restricted platform that fails its core mission

**Warning signs:**
- The pipeline ingests fields like `correo_supervisor`, `telefono_interventor`, `direccion_domicilio` without reviewing them
- No data classification pass has been done on each source dataset's field list
- Platform allows free-text search returning full natural person records without authentication

**Prevention:**
- Before ingesting any dataset, produce a field classification inventory: mark each field as `PUBLICA | SEMIPRIVADA | PRIVADA | SENSIBLE`
- Fields classified as PRIVADA or SENSIBLE: do not store in Neo4j, or store encrypted and never expose via API
- Fields for public servants in their official capacity (nombre, cargo, entidad, NIT like cedula when acting as contractor): treated as public under Art. 3 of Ley 1712/2014 and Art. 26 of Ley 1581/2012
- Personal email, home address, personal phone: do not ingest
- Implement a `privacy_mode: strict` flag (consistent with br-acc's "public-safe defaults") that is the default for any deployment without explicit institutional credentials
- Consult SIC guidance documents on datos públicos before the first production deployment

**Phase to address:** Phase 1 (data modeling) and Phase 3 (API design). Cannot be retrofitted after data is already exposed.

---

### Pitfall 8: "Build It and They Will Come" — No User Research Before Building

**What goes wrong:** The platform is built around what the data makes technically possible (graph traversal, community detection, centrality scores) rather than what journalists, veedurías, or ONGs actually need to do their work. The result is a sophisticated tool that requires Neo4j expertise to use, with no adoption.

**Why it happens:** Harvard's Ash Center research on civic technology found this is the dominant failure mode: "a large digital cemetery of fascinating applications" built by technologists who prioritized technical capability over user workflow. The research explicitly found that "to the extent that civic technology has failed, it has not been because of insufficient data, but because it often ignores power and collective action."

**Consequences:**
- Platform is technically correct but unused
- Features built for technical elegance (e.g., Cypher query interface) replace features needed for actual use (e.g., "show me all contracts above X pesos in municipality Y awarded to companies created less than 6 months before the contract")
- Journalists use PACO or manual SECOP searches instead

**Warning signs:**
- No journalist or veeduría has been consulted before sprint planning
- Feature roadmap items are defined by what the data contains, not by documented user tasks
- Platform has no concept of a "saved investigation" or "exported report"

**Prevention:**
- Conduct at least 3 user interviews with target users (investigative journalists, veeduría ciudadana members, ONG researchers) before designing the frontend
- Define 5 concrete "investigation stories" (narratives a user wants to tell) and ensure each one is achievable in under 5 clicks from the home page
- Prioritize search-and-filter workflows over raw graph exploration for non-technical users; graph visualization should be a secondary layer, not the primary entry point
- Look at PACO's interface (portal.paco.gov.co) — understand what it does well and where it fails users

**Phase to address:** Pre-development research (before Phase 1 feature work). Revisit after Phase 3 with usability testing.

---

### Pitfall 9: datos.gov.co API Treated as a Reliable Production Dependency

**What goes wrong:** The pipeline runs on a schedule and makes synchronous Socrata API calls at runtime. datos.gov.co goes offline (which happens — Colombia Compra Eficiente documented a 4x increase in SECOP incidents between 2022 and 2023), the pipeline crashes mid-run, and the graph is in a partially-updated state.

**Why it happens:** Government open data portals are not operated with the same SLAs as commercial APIs. br-acc explicitly acknowledges it cannot "guarantee uptime/stability of every third-party public portal." Designing for this is easy to defer.

**Consequences:**
- Partial ingestion leaves the graph in an inconsistent state (some contracts updated, related entities not)
- Automatic retries hammer the API during a transient outage, triggering rate limiting
- No way to audit which records were successfully ingested vs. missed

**Prevention:**
- Always download raw API responses to disk before any transformation: treat the raw JSON/CSV as the canonical input, not the live API
- Implement idempotent pipeline stages: a stage that crashes mid-run must be safely re-runnable without creating duplicates
- Track ingestion state per dataset per date range in a simple state table (SQLite or Postgres): `{dataset_id, date_range, status, row_count, timestamp}`
- Set Socrata request timeouts at 30 seconds; implement exponential backoff with jitter on 429 and 5xx responses
- Never run full re-ingestion and incremental update in the same transaction window

**Phase to address:** Phase 1 (ETL pipeline architecture).

---

## Minor Pitfalls

---

### Pitfall 10: Neo4j Community Edition Licensing Assumption for Production

**What goes wrong:** The project uses Neo4j Community Edition (as br-acc does) and plans a production deployment. At scale, the team discovers Community Edition has no hot backup capability and no clustering support — meaning scheduled maintenance requires taking the database offline. For an open civic platform, this creates availability gaps.

**Prevention:**
- Document this limitation explicitly in deployment docs
- Plan maintenance windows for off-peak hours (early Sunday morning Colombia time)
- Use Neo4j's `neo4j-admin dump` for cold backups on a schedule; test restore procedure before going live
- If high availability becomes a hard requirement, evaluate Neo4j's new free tier options or consider ArangoDB/Memgraph as alternatives (both have clustering in their open-source editions)

**Phase to address:** Phase 3 (infrastructure/deployment).

---

### Pitfall 11: Cypher Query Complexity Grows Unbounded Without a Query Budget

**What goes wrong:** Pattern detection features require increasingly complex Cypher queries (find all contractors who share a legal representative with a sanctioned company and have won contracts from the same entity in the last 3 years). These queries run against the full graph and time out or consume all heap memory in production.

**Warning signs:**
- Pattern detection queries that work on a 10K-node test graph fail on the production 10M-node graph
- Neo4j logs show `OutOfMemory` or `TransactionMemoryPoolException`

**Prevention:**
- Set a query execution time limit in neo4j.conf: `db.transaction.timeout=30s`
- Implement all pattern detection queries as offline batch jobs (Python + neo4j-driver with streaming), not synchronous API calls
- Use Neo4j GDS (Graph Data Science) library for community detection and centrality — it is optimized for large graphs and runs projections rather than full graph scans
- Profile every pattern detection query against a realistic data volume (at minimum 500K contracts) before shipping

**Phase to address:** Phase 3 (pattern detection feature).

---

### Pitfall 12: RUES and Contraloria Data Treated Symmetrically with Socrata Sources

**What goes wrong:** The pipeline architecture assumes all data sources are Socrata APIs. RUES (registros empresariales) requires institutional credentials and has no free API. The Contraloria Boletín de Responsables Fiscales is a quarterly PDF. Treating these as equivalent to SECOP leads to either hardcoded credentials in the codebase or broken pipelines that silently produce empty results.

**Prevention:**
- Clearly separate source types in architecture: `Type A: Socrata API (automated)`, `Type B: Bulk download + parse (semi-automated)`, `Type C: Third-party credential (gated, future)`
- Contraloria PDF: implement a specific parser pipeline with an explicit "last parsed date" stamp; alert when the stamp is > 90 days old
- RUES: implement as a stub adapter with a clear "NOT CONFIGURED" status; do not mix RUES-dependent features into MVP
- Never commit API credentials; use environment variables with a documented `.env.example`

**Phase to address:** Phase 1 (source connector architecture).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| ETL / Data ingestion | Entity resolution not started, NIT normalization deferred | Enforce: no data in Neo4j until normalization strategy is documented and tested |
| Graph schema design | Super nodes from municipality/sector categoricals | Review every planned node type: if it has < 10,000 distinct values and > 100K relationships, make it a property |
| SECOP I + SECOP II join | Schema differences cause silent duplicates or wrong joins | Separate ETL pipelines, provenance field mandatory on every node |
| Legal compliance | Ley 1581 scope applied incorrectly | Field-by-field privacy classification before ingest; legal review before public launch |
| Pattern detection feature | Complex Cypher queries OOM in production | Offline batch execution only; never synchronous API call; test at realistic volume |
| Frontend / UI design | Graph visualization implies accusation | Mandatory: source attribution on every data point, explicit "not an accusation" framing |
| Public deployment | datos.gov.co availability | Idempotent pipelines + raw response archival mandatory; no synchronous API dependency at request time |
| User adoption | Built for data, not for users | Journalist user research before frontend design begins; 5 concrete investigation stories must be achievable |

---

## Sources

- [Neo4j: Graph Modeling — All About Super Nodes](https://medium.com/neo4j/graph-modeling-all-about-super-nodes-d6ad7e11015b) — HIGH confidence (official Neo4j blog)
- [Neo4j Super Node Performance Issues — Justin Boylan-Toomey](https://jboylantoomey.com/post/neo4j-super-node-performance-issues) — MEDIUM confidence (practitioner case study, verified against Neo4j docs)
- [Neo4j Entity Resolution GitHub Examples](https://github.com/neo4j-graph-examples/entity-resolution) — HIGH confidence (official Neo4j)
- [ICIJ Offshore Leaks Database — How to Use](https://offshoreleaks.icij.org/pages/howtouse) — HIGH confidence (official ICIJ documentation)
- [ICIJ: Three Key Lessons from Managing the Biggest Journalism Projects](https://www.icij.org/investigations/pandora-papers/three-key-lessons-from-managing-the-biggest-journalism-projects-in-history/) — HIGH confidence (ICIJ primary source)
- [Harvard Ash Center: Transparency is Insufficient — Lessons from Civic Technology for Anticorruption](https://ash.harvard.edu/articles/transparency-is-insufficient-lessons-from-civic-technology-for-anticorruption/) — HIGH confidence (peer-reviewed research)
- [Open Contracting Data Standard — Assessing Data Quality](https://standard.open-contracting.org/latest/en/guidance/publish/quality/) — HIGH confidence (official OCDS documentation)
- [br-acc GitHub Repository — README](https://github.com/World-Open-Graph/br-acc) — HIGH confidence (primary source, direct reference project)
- [Colombia Compra Eficiente — Manual de Datos Abiertos SECOP 2024](https://www.colombiacompra.gov.co/wp-content/uploads/2024/09/manual_de_datos_abiertos_actualizado.pdf) — HIGH confidence (official government source)
- [Socrata SODA API — Pagination Documentation](https://dev.socrata.com/docs/queries/limit.html) — HIGH confidence (official Socrata docs)
- [Socrata — Throttling Limits Clarification](https://dev.socrata.com/changelog/2016/06/04/clarification-of-throttling-limits.html) — MEDIUM confidence (older doc, behavior confirmed current)
- [Neo4j: Best Practices for Large Updates](https://neo4j.com/blog/nodes/nodes-2019-best-practices-to-make-large-updates-in-neo4j/) — HIGH confidence (official Neo4j)
- [Ley 1581 de 2012 — Gestor Normativo Función Pública](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981) — HIGH confidence (official Colombian law text)
- [SECOP: Colombia Compra Eficiente acknowledges system incidents 4,552 (2022) to 17,787 (2023)](https://www.colombiacompra.gov.co/archivos/16418) — MEDIUM confidence (official source, specific numbers from secondary reporting)
- [Splink — Probabilistic Record Linkage (UK Ministry of Justice)](https://moj-analytical-services.github.io/splink/index.html) — HIGH confidence (official project documentation)
