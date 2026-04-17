# Phase 2: Full ETL - Research

**Researched:** 2026-04-09
**Domain:** Socrata SODA API field mapping, Neo4j Cypher MERGE patterns, Colombian public data schema
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Entity Linking**
- Deterministic matching by cedula (personas) and NIT (empresas) — no fuzzy matching needed
- Reuse normalize_nit() and normalize_cedula() from etl/normalizers/common.py (Phase 1)
- MERGE on normalized keys ensures automatic linking when same entity appears in multiple sources
- Records with null/invalid identifiers are skipped (null sentinel policy from Phase 1)

**Super Node Prevention**
- Categorical values (municipio, departamento, sector, tipo_contrato, modalidad) stored as node properties, NOT as separate nodes with relationships
- This avoids the super node problem entirely — no categorical node can accumulate relationships
- If a categorical query is needed, use Neo4j indexes on properties instead

**Pipeline Execution Order**
- SECOP II Contratos first (extends existing contract graph)
- SIGEP second (adds public servants, links to contracts by cedula)
- SIRI third (adds sanctions, links to persons/companies by cedula/NIT)
- SECOP Multas last (adds fines, links to existing contractors)
- Cross-linking happens implicitly via MERGE on shared keys — no separate linking step needed

**Pipeline Pattern**
- All new pipelines extend BasePipeline from etl/base.py (Phase 1 pattern)
- Same three-pass MERGE pattern: entities first, then relationships
- Same provenance metadata (fuente, ingested_at, url_fuente) on every node
- Same incremental state via etl/state.py

### Claude's Discretion
- Field mapping for each new dataset (inspect actual API responses)
- Batch sizes and pagination strategy per source
- Error handling for malformed records
- Dataset-specific normalization beyond NIT/cedula

### Deferred Ideas (OUT OF SCOPE)
None — phase scope is clear.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ETL-02 | Pipeline de ingesta SECOP II Contratos Electronicos (jbjy-vk9h) | Field map verified via live API; id_contrato is globally unique (no composite key needed unlike SECOP I) |
| ETL-03 | Pipeline de ingesta SIGEP servidores publicos (2jzx-383z) | Field map verified; numerodeidentificacion is the cedula key; nombre field contains only ID (no name data) |
| ETL-04 | Pipeline de ingesta SIRI sanciones disciplinarias Procuraduria (iaeu-rcn6) | Field map verified; all records are natural persons (cedula only, no NIT/empresa records found); numero_siri is unique key |
| ETL-05 | Pipeline de ingesta Multas y Sanciones SECOP (4n4q-k399) | Field map verified; documento_contratista may be cedula or NIT (no discriminator field); composite key needed for id_sancion |
| ETL-06 | Entity linking cross-source by cedula/NIT | Implicit via MERGE on normalized keys — no separate linking pipeline step needed |
</phase_requirements>

---

## Summary

Phase 2 adds four new Socrata pipeline modules. All follow the exact pattern of `etl/sources/secop_integrado.py` established in Phase 1 — extending `BasePipeline`, using `normalize_nit()` and `normalize_cedula()` from `etl/normalizers/common.py`, and writing via `Neo4jLoader.merge_batch()`. Cross-source entity linking (ETL-06) requires no dedicated pipeline step: MERGE on shared normalized identifiers creates the links automatically.

The critical new discoveries from live API inspection are: (1) SIGEP's `nombre` field contains only the ID number, not the person's name — the dataset is privacy-redacted and provides no name data for public servants; (2) SIRI contains only natural persons (cedula-identified) — no empresa/NIT records were found in the dataset, so SIRI only produces `(Persona)-[:SANCIONADO]->(Sancion)` relationships; (3) SECOP Multas' `documento_contratista` field has no document-type discriminator — both cedulas and NITs appear with no label distinguishing them; (4) SIRI `numero_identificacion` contains trailing whitespace that must be stripped before normalization.

The schema already has all required constraints (`persona_cedula`, `empresa_nit`, `sancion_id`, etc.). No new constraints are needed. `etl/run.py` must be extended to register the four new pipeline names.

**Primary recommendation:** Implement each pipeline as a direct structural clone of `secop_integrado.py`, adapting only the field mapping, DATASET_ID, and Cypher statements. The shared infrastructure (BasePipeline, Neo4jLoader, normalizers, state) is complete and correct.

---

## Project Constraints (from CLAUDE.md)

| Directive | Source | Impact on Phase 2 |
|-----------|--------|-------------------|
| Stack: Neo4j + FastAPI + Python | CLAUDE.md | Use existing stack only; no new dependencies |
| Solo fuentes publicas gratuitas (Socrata API) | CLAUDE.md | All four datasets are free Socrata endpoints — compliant |
| Ley 1581/2012 — no exponer datos personales protegidos | CLAUDE.md | SIGEP: nombre field is already ID-only (redacted); SIRI cedulas are SEMIPRIVADA; apply PUBLIC_MODE guards on cedulas |
| Docker Compose deployment | CLAUDE.md | No new containers needed for ETL |
| Interfaz en espanol | CLAUDE.md | Log messages and comments may be in English; field names match Spanish source |
| No inline normalization — use etl.normalizers.common | codebase convention | All NIT/cedula normalization must delegate to the shared module |
| MERGE anti-pattern: never merge full (a)-[:R]->(b) pattern | ARCHITECTURE.md | Always MERGE each node separately, then MERGE the relationship |
| verify_constraints() called at every Neo4jLoader startup | codebase convention | No new code required; existing loader enforces this |

---

## Standard Stack

No new libraries are required for Phase 2. All dependencies are installed from Phase 1.

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | latest | Async Socrata pagination | Same client used in secop_integrado.py |
| polars | 1.39.x | DataFrame page processing | Same pattern — infer_schema_length=None for variable schemas |
| neo4j (driver) | 6.1.0 | Async MERGE writes | Neo4jLoader wraps it; no changes needed |
| etl.normalizers.common | (internal) | NIT/cedula normalization | Mandatory — no inline normalization allowed |
| etl.base.BasePipeline | (internal) | Abstract pipeline base class | All four new pipelines extend this |

### No new dependencies needed
Phase 2 is purely additive — four new files under `etl/sources/` and a registry update in `etl/run.py`.

---

## Dataset Inventory (Live API Verified)

### Dataset Sizes (verified 2026-04-09)

| Dataset | ID | Approximate Rows | Sort Field for Pagination |
|---------|-----|-----------------|--------------------------|
| SECOP II Contratos | jbjy-vk9h | Large (count timed out; est. 1M+) | fecha_de_firma |
| SIGEP Servidores Publicos | 2jzx-383z | 265,339 | fecha_de_vinculaci_n |
| SIRI Sanciones | iaeu-rcn6 | 44,159 | fecha_efectos_juridicos |
| SECOP Multas | 4n4q-k399 | 1,703 | fecha_de_publicacion |

---

## Architecture Patterns

### Recommended Project Structure (additive)
```
etl/
├── sources/
│   ├── secop_integrado.py       # Phase 1 — reference implementation
│   ├── secop_ii_contratos.py    # Phase 2 — new
│   ├── sigep_servidores.py      # Phase 2 — new
│   ├── siri_sanciones.py        # Phase 2 — new
│   └── secop_multas.py          # Phase 2 — new
├── run.py                       # extend PIPELINES dict with 4 new entries
└── ...
```

### Pattern: Three-Pass MERGE (inherited from Phase 1)

Every pipeline that creates multiple node types uses the established three-pass pattern:

**Pass 1:** MERGE primary entity nodes + secondary entity nodes (e.g., EntidadPublica, Contrato)
**Pass 2:** MERGE contractor/person nodes for a specific type (e.g., Empresa rows only)
**Pass 3:** MERGE contractor/person nodes for the other type (e.g., Persona rows only)

Each MERGE pass is a separate `loader.merge_batch()` call with its own Cypher statement. Never combine node and relationship MERGEs in one pattern.

### Pattern: Pagination Sort Field

Use a stable date field with `$order=<field> ASC` to prevent offset drift (Pitfall 5 from PITFALLS.md). Each dataset has a different sort field:

```python
"$order": "fecha_de_firma ASC"           # SECOP II
"$order": "fecha_de_vinculaci_n ASC"     # SIGEP
"$order": "fecha_efectos_juridicos ASC"  # SIRI
"$order": "fecha_de_publicacion ASC"     # Multas
```

For incremental runs, use `$where=<sort_field> > '{last_run_at}'`.

### Anti-Patterns to Avoid
- **Inline normalization:** Any `re.sub()` or string manipulation on NIT/cedula inside a source file — use `normalize_nit()` from `etl.normalizers.common`
- **Combined node+relationship MERGE:** `MERGE (a:Empresa)-[:EJECUTA]->(c:Contrato)` — always two separate statements
- **MERGE on null key:** Never call `MERGE (p:Persona {cedula: None})` — skip records where normalized key is None
- **Categoricals as nodes:** `(:Municipio)`, `(:Sector)`, `(:TipoContrato)` are forbidden — store as properties on the primary node

---

## Field Maps (Live API Verified)

### ETL-02: SECOP II Contratos (jbjy-vk9h)

**Dataset size:** ~1M+ rows (count query timed out)
**Sort field:** `fecha_de_firma`
**Unique key:** `id_contrato` — format is `CO1.PCCNTR.<number>`, globally unique in the SECOP II system (no composite key needed, unlike SECOP I which uses `numero + origen`)

**Field map (81 fields total; mapped fields below):**

| API Field | Neo4j Target | Node | Notes |
|-----------|-------------|------|-------|
| id_contrato | id_contrato | Contrato | Primary MERGE key — already a stable unique ID |
| codigo_entidad | codigo_entidad | EntidadPublica | MERGE key for entity |
| nombre_entidad | nombre | EntidadPublica | Display name |
| nit_entidad | nit | EntidadPublica | normalize_nit() |
| departamento | departamento | EntidadPublica property | Categorical — property, not node |
| ciudad | municipio | EntidadPublica property | Categorical — property, not node |
| sector | sector | EntidadPublica property | Categorical — property, not node |
| orden | orden | EntidadPublica property | Categorical — property, not node |
| tipodocproveedor | (classifier) | — | Classify Empresa vs Persona; values: "NIT", "Cédula de Ciudadanía" |
| documento_proveedor | nit OR cedula | Empresa or Persona | normalize_nit() for both |
| proveedor_adjudicado | razon_social / nombre | Empresa or Persona | Display name |
| codigo_proveedor | codigo_proveedor | Empresa or Persona | Secondary identifier; store as property |
| tipo_de_contrato | tipo | Contrato property | Categorical — property, not node |
| modalidad_de_contratacion | modalidad | Contrato property | Categorical — property, not node |
| estado_contrato | estado | Contrato property | |
| fecha_de_firma | fecha_firma | Contrato | Pagination sort field |
| fecha_de_inicio_del_contrato | fecha_inicio | Contrato | |
| fecha_de_fin_del_contrato | fecha_fin | Contrato | |
| valor_del_contrato | valor | Contrato | Parse as float (integer string, no dots as thousands separator in SECOPII) |
| objeto_del_contrato | objeto | Contrato | Long text field |
| urlproceso | url_fuente | Contrato | Provenance URL |
| descripcion_del_proceso | descripcion | Contrato | May be null |
| proceso_de_compra | numero_proceso | Contrato | Process reference |
| ultima_actualizacion | (skip) | — | Update timestamp; not needed for graph |

**Fields to skip (too many, privacy risk, or categorical):**
`es_grupo`, `es_pyme`, `habilita_pago_adelantado`, `liquidaci_n`, `obligaci_n_ambiental`, `obligaciones_postconsumo`, `reversion`, `origen_de_los_recursos`, `destino_gasto`, `valor_de_pago_adelantado`, `valor_facturado`, `valor_pendiente_de_pago`, `valor_pagado`, `valor_amortizado`, `valor_pendiente_de`, `valor_pendiente_de_ejecucion`, `saldo_cdp`, `saldo_vigencia`, `espostconflicto`, `dias_adicionados`, `puntos_del_acuerdo`, `pilares_del_acuerdo`, `nombre_representante_legal`, `identificaci_n_representante_legal`, `nombre_ordenador_del_gasto`, `n_mero_de_documento_ordenador_del_gasto`, `nombre_supervisor`, `n_mero_de_documento_supervisor`, `nombre_ordenador_de_pago`, `n_mero_de_documento_ordenador_de_pago`, `nombre_del_banco`, `tipo_de_cuenta`, `n_mero_de_cuenta`, `documentos_tipo`, `descripcion_documentos_tipo`

**Privacy classification:**
- `nombre_representante_legal`, `identificaci_n_representante_legal` — SEMIPRIVADA; omit in PUBLIC_MODE
- `nombre_supervisor`, `nombre_ordenador_del_gasto` — SEMIPRIVADA; omit
- Bank account fields (`nombre_del_banco`, `tipo_de_cuenta`, `n_mero_de_cuenta`) — PRIVADA; never store

**tipodocproveedor values observed:** "NIT", "Cédula de Ciudadanía"
These map directly to the existing `classify_proveedor_type()` function. Verify the function handles the exact accent/capitalization of "Cédula de Ciudadanía" (note: the existing function uses lowercase comparison, so this is safe).

**Graph relationships:**
```
(EntidadPublica)-[:ADJUDICO]->(Contrato)
(Empresa)-[:EJECUTA]->(Contrato)        # when tipodocproveedor = "NIT"
(Persona)-[:EJECUTA]->(Contrato)        # when tipodocproveedor = "Cédula de Ciudadanía"
```

---

### ETL-03: SIGEP Servidores Publicos (2jzx-383z)

**Dataset size:** 265,339 rows
**Sort field:** `fecha_de_vinculaci_n` (note: accent in API field name is absent — actual field is `fecha_de_vinculaci_n` not `fecha_de_vinculación`)
**Unique key for Persona:** `numerodeidentificacion` (cedula) — normalize_cedula()
**Unique key for ServidorPublico employment record:** No natural composite key; use `numerodeidentificacion + "_" + codigosigep` as a synthetic key for deduplication if needed

**CRITICAL DISCOVERY — nombre field:**
The `nombre` field in SIGEP does NOT contain the person's name. It is a copy of `numerodeidentificacion`. This dataset has been anonymized/privacy-redacted. The only personal name data available is `denominacionempleoactual` (job title) and `dependenciaempleoactual` (department), not the person's name. **Do not populate `Persona.nombre` from SIGEP's `nombre` field.**

Instead:
- Merge `Persona` on `cedula = normalize_cedula(numerodeidentificacion)`
- Do NOT set `nombre` from SIGEP data (it will be filled from SECOP if the person appears there)
- Store employment-specific data as properties on the employment relationship or as a separate `ServidorPublico` fact

**Field map (22 fields total):**

| API Field | Neo4j Target | Node/Rel | Notes |
|-----------|-------------|---------|-------|
| numerodeidentificacion | cedula | Persona | MERGE key; normalize_cedula() |
| nombre | (skip) | — | Always equals numerodeidentificacion; do not use |
| sexo | sexo | Persona property | "MASCULINO"/"FEMENINO" |
| departamentodenacimiento | departamento_nacimiento | Persona property | Categorical — property |
| municipiodenacimiento | municipio_nacimiento | Persona property | Categorical — property |
| nombreentidad | nombre | EntidadPublica | Name for the employing entity |
| codigosigep | codigo_sigep | EMPLEA rel property | NOT a unique person key — institution code |
| orden | orden | EntidadPublica property | Categorical |
| naturalezajuridica | naturaleza | EntidadPublica property | Categorical |
| tipodenombramiento | tipo_nombramiento | EMPLEA rel property | How the servant was appointed |
| niveljerarquicoempleo | nivel_jerarquico | EMPLEA rel property | Job level: ASISTENCIAL, TECNICO, PROFESIONAL, etc. |
| denominacionempleoactual | cargo | EMPLEA rel property | Current position title |
| dependenciaempleoactual | dependencia | EMPLEA rel property | Department/division |
| asignacionbasicasalarial | salario_basico | EMPLEA rel property | String with commas as thousands separator — strip before float parse |
| fecha_de_vinculaci_n | fecha_vinculacion | EMPLEA rel property | ISO8601 datetime string |
| mesesdeexperienciapublico | (skip or property) | Persona | Low value for graph analysis; store if space allows |
| mesesdeexperienciaprivado | (skip) | — | |
| mesesdeexperienciadocente | (skip) | — | |
| mesesdeexperienciaindependiente | (skip) | — | |
| niveleducativo | nivel_educativo | Persona property | Semicolon-delimited string (multiple degrees) |
| iddepartamentodenacimiento | (skip) | — | Numeric code; departamentodenacimiento is sufficient |
| idmunicipiodenacimiento | (skip) | — | Numeric code; municipiodenacimiento is sufficient |

**EntidadPublica MERGE key problem:** SIGEP does not expose a `codigo_entidad` equivalent. The only identifier for the employing entity is `nombreentidad` (string name). This creates a matching challenge — the same entity may appear in SECOP with its `codigo_entidad` but in SIGEP only with its name.

**Recommended approach for SIGEP's EntidadPublica:**
Do not attempt to MERGE SIGEP entities into the same `EntidadPublica` node as SECOP entities by name (string matching is unreliable). Instead, create a separate relationship type or use `codigosigep` as a secondary property on the EntidadPublica node. Accept that SIGEP entities may create new `EntidadPublica` nodes that do not link to SECOP entities until Phase 3 (API layer) adds a reconciliation step. The graph schema uses `codigo_entidad` as the unique constraint — SIGEP entities without a `codigo_entidad` cannot MERGE into existing EntidadPublica nodes.

**Practical decision (Claude's discretion):** Create a `ServidorPublicoEmpleo` intermediate approach using `(Persona)-[:EMPLEA_EN {cargo, fecha_vinculacion, fuente}]->(EntidadPublica)` where EntidadPublica is matched by `nombre` (best-effort, lowercase-stripped) rather than `codigo_entidad`. Accept potential duplicates — the constraint is only on `codigo_entidad`, so an EntidadPublica without that field won't collide. Alternatively, use a `{nombre_entidad: x}` property-only approach without constraint enforcement. See Open Questions.

**Graph relationships:**
```
(Persona)-[:EMPLEA_EN]->(EntidadPublica)
```

**asignacionbasicasalarial format:** Stored as a string with comma as thousands separator: `"1,440,300"`. Must strip commas before float parse. Unlike SECOP I (dots as thousands separator), SIGEP uses commas.

---

### ETL-04: SIRI Sanciones Disciplinarias (iaeu-rcn6)

**Dataset size:** 44,159 rows
**Sort field:** `fecha_efectos_juridicos`
**Unique key:** `numero_siri` — appears to be globally unique per sanction record

**CRITICAL DISCOVERY — persona natural only:**
After querying distinct `calidad_persona` and `tipo_identificacion` combinations across the full dataset, only the following appear:
- SERVIDOR PUBLICO / cedula
- MIEMBRO DE LA FUERZA PUBLICA / cedula
- CONTRATISTA / cedula
- PARTICULAR QUE EJERCE FUNCION PUBLICA / cedula or cedula extranjeria
- PARTICULAR / cedula
- NA / cedula

No NIT-type identifiers were found. SIRI sanctions are always linked to natural persons (cedula). No `Empresa` nodes are created from SIRI. This simplifies the pipeline to a single MERGE pass for `Persona`.

**CRITICAL DISCOVERY — trailing whitespace in numero_identificacion:**
Live API data shows `numero_identificacion` padded with trailing spaces: `"7534386        "`. This must be stripped with `.strip()` BEFORE passing to `normalize_cedula()`.

**CRITICAL DISCOVERY — date format:**
`fecha_efectos_juridicos` is formatted as `"DD/MM/YYYY"` (e.g., `"22/04/2005"`), not ISO8601. This must be parsed/stored as-is (string) or converted before use in Cypher.

**Field map (24 fields total):**

| API Field | Neo4j Target | Node | Notes |
|-----------|-------------|------|-------|
| numero_siri | id_sancion | Sancion | MERGE key; already exists in schema constraint `sancion_id` |
| tipo_inhabilidad | tipo_inhabilidad | Sancion property | Broad sanction category |
| calidad_persona | calidad_persona | Sancion property | Role of sanctioned person (CONTRATISTA, SERVIDOR PUBLICO, etc.) |
| tipo_identificacion | (classifier) | — | Always "1" (cedula) in practice; validate |
| nombre_tipo_identificacion | (skip) | — | Text version of tipo_identificacion; redundant |
| numero_identificacion | cedula | Persona | STRIP TRAILING WHITESPACE then normalize_cedula() |
| primer_apellido | apellido1 | Persona property | Store if non-null; may be missing |
| segundo_apellido | apellido2 | Persona property | May be null |
| primer_nombre | nombre1 | Persona property | May be missing or contain "/" (data quality issues) |
| segundo_nombre | nombre2 | Persona property | May be null |
| cargo | cargo_sancionado | Sancion property | Position held at time of sanction |
| lugar_hechos_departamento | departamento | Sancion property | Categorical — property |
| lugar_hechos_municipio | municipio | Sancion property | Categorical — property |
| sanciones | tipo_sancion | Sancion property | Long text enum; 17+ variants including MULTA, DESTITUCION, INHABILIDAD, etc. |
| duracion_anos | duracion_anos | Sancion property | Integer string; may be empty for DESTITUCION |
| duracion_mes | duracion_mes | Sancion property | May be empty |
| duracion_dias | duracion_dias | Sancion property | May be empty |
| providencia | providencia | Sancion property | Legal resolution reference |
| autoridad | autoridad | Sancion property | Sanctioning authority name |
| fecha_efectos_juridicos | fecha_efectos | Sancion property | DD/MM/YYYY format — store as string |
| numero_proceso | numero_proceso | Sancion property | Administrative process number |
| entidad_sancionado | entidad | Sancion property | Entity where the person worked |
| entidad_departamento | entidad_departamento | Sancion property | Categorical — property |
| entidad_municipio | entidad_municipio | Sancion property | Categorical — property |

**Persona name assembly:** SIRI has the most complete name data of all four datasets. Assemble a composite `nombre` property from `primer_nombre + " " + segundo_nombre + " " + primer_apellido + " " + segundo_apellido` (skip null parts). ON MATCH: do NOT overwrite an existing `nombre` on a Persona that may have already been created from SECOP with a better name.

**Graph relationships:**
```
(Persona)-[:SANCIONADO]->(Sancion)
```

**Schema note:** The `sancion_id` constraint already exists in `infra/neo4j/schema.cypher`. The constraint requires `Sancion.id_sancion`. Use `numero_siri` as the value for `id_sancion`. No schema changes needed.

---

### ETL-05: SECOP Multas y Sanciones (4n4q-k399)

**Dataset size:** 1,703 rows (small — single-pass load is feasible)
**Sort field:** `fecha_de_publicacion`
**Unique key:** No natural single-field key. Composite: `nombre_entidad + numero_de_resolucion + documento_contratista` is the most stable combination. Store as `id_sancion = f"{nit_entidad}_{numero_de_resolucion}_{doc_contratista}"`.

**CRITICAL DISCOVERY — no document type discriminator:**
`documento_contratista` contains both cedulas (natural persons) and NITs (empresas), but there is no `tipodocproveedor`-style field in this dataset. There is no reliable way to distinguish cedula from NIT based on the number alone.

**Recommended approach:** Attempt to classify by number length and prefix heuristic (NITs in Colombia are typically 9 digits; cedulas range 6-10 digits), but this is imprecise. The safer approach is to attempt MERGE on both `Empresa` and `Persona` as a two-pass operation — if the number matches an existing `Empresa.nit`, the relationship is created there; if it matches an existing `Persona.cedula`, it goes there. If neither exists, create a new node based on the name heuristic: if `nombre_contratista` contains legal suffixes (S.A., LTDA, SAS, UNION TEMPORAL, CONSORCIO), treat as Empresa; otherwise treat as Persona.

**Field map (14 fields total):**

| API Field | Neo4j Target | Node | Notes |
|-----------|-------------|------|-------|
| nit_entidad | nit | EntidadPublica | normalize_nit(); may contain hyphen (e.g., "890000858-1") |
| nombre_entidad | nombre | EntidadPublica | |
| nivel | nivel | EntidadPublica property | Categorical |
| orden | orden | EntidadPublica property | Categorical |
| municipio | municipio | EntidadPublica property | Categorical |
| numero_de_resolucion | numero_resolucion | Sancion property | Resolution number |
| documento_contratista | nit OR cedula | Empresa or Persona | No discriminator — see approach above |
| nombre_contratista | razon_social / nombre | Empresa or Persona | Use name heuristic to classify |
| numero_de_contrato | numero_contrato | Sancion property | May link to existing Contrato; use as reference, not FK |
| valor_sancion | valor | Sancion property | Integer string — parse as float |
| fecha_de_publicacion | fecha_publicacion | Sancion property | ISO8601 datetime |
| fecha_de_firmeza | fecha_firmeza | Sancion property | ISO8601 datetime |
| fecha_de_cargue | fecha_cargue | Sancion property | ISO8601 datetime |
| ruta_de_proceso | url_fuente | Sancion property | URL to contratos.gov.co process |

**Composite id_sancion construction:**
```python
id_sancion = f"{normalize_nit(nit_entidad) or ''}_{numero_de_resolucion}_{doc_clean}"
```
This is needed because Multas has no native unique ID. The `sancion_id` constraint in schema.cypher already covers `:Sancion {id_sancion}`.

**EntidadPublica MERGE:** `nit_entidad` exists in this dataset (unlike SIGEP). However, the constraint on EntidadPublica uses `codigo_entidad`, not `nit`. Do not MERGE on `nit_entidad` alone. Instead, use `nit_entidad` as a property lookup: `MATCH (ent:EntidadPublica {nit: $nit_entidad})` after SECOP II populates those nodes. If no match, create a minimal EntidadPublica with only `nit` set and mark it for reconciliation.

**Graph relationships:**
```
(EntidadPublica)-[:IMPUSO]->(Sancion)
(Empresa)-[:MULTADO]->(Sancion)     # when classified as empresa
(Persona)-[:MULTADO]->(Sancion)     # when classified as persona
```

**Note on relationship naming:** Use `:MULTADO` for Multas-sourced sanctions to distinguish from `:SANCIONADO` from SIRI. Both types point to `:Sancion` nodes but have different semantic origins.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| NIT/cedula normalization | Custom regex per pipeline | `normalize_nit()` / `normalize_cedula()` from `etl.normalizers.common` | Already handles check digit, dots, leading zeros, None sentinel |
| Company vs person classification | Length/prefix heuristics inline | `classify_proveedor_type()` for SECOP II; extend for Multas | Existing function handles the NIT vs cedula de ciudadania distinction |
| Socrata pagination | Custom offset tracker | `BasePipeline.extract()` pattern from secop_integrado.py | Handles offset drift prevention, crash recovery via state |
| Neo4j MERGE batching | Direct session.run() per record | `Neo4jLoader.merge_batch()` | Handles batching, connection pooling, retries |
| Constraint verification | Manual schema check | `verify_constraints()` in `neo4j_loader.py` | Already called at every startup; abort if missing |
| String normalization for razon_social dedup | Custom per-pipeline | `normalize_razon_social()` | Handles accents, legal suffixes, whitespace collapse |

---

## Common Pitfalls

### Pitfall 1: SIGEP nombre Field Is Not a Name
**What goes wrong:** Developer reads the `nombre` field from SIGEP and populates `Persona.nombre` with what appears to be a name but is actually the ID number again (e.g., `"1045229288"`).
**Why it happens:** The field is named `nombre` in the Socrata schema but the dataset has been anonymized — every person's "name" is replaced with their ID number.
**How to avoid:** Skip the `nombre` field entirely. If `Persona.nombre` is needed, it will be populated from SECOP data when the same cedula appears there.
**Warning signs:** `Persona.nombre` values that look like 8-10 digit numbers.

### Pitfall 2: SIRI numero_identificacion Has Trailing Spaces
**What goes wrong:** `normalize_cedula("7534386        ")` fails because the cleaned string still produces a valid number, but `normalize_nit()` strips internal dots/spaces but leaves trailing content unless `.strip()` is called first.
**Why it happens:** Socrata returns the field with trailing whitespace padding from the source system.
**How to avoid:** Always call `.strip()` on `numero_identificacion` BEFORE passing to `normalize_cedula()`.
**Code pattern:**
```python
cedula_raw = (row.get("numero_identificacion") or "").strip()
cedula = normalize_cedula(cedula_raw)
```

### Pitfall 3: SECOP II id_contrato Looks Different But Is Globally Unique
**What goes wrong:** Developer sees `id_contrato = "CO1.PCCNTR.8560835"` and tries to build a composite key (like SECOP I's `numero + origen`), creating duplicate Contrato nodes.
**Why it happens:** SECOP I required a composite key to prevent cross-system collisions. SECOP II's `id_contrato` is already a system-assigned globally unique identifier.
**How to avoid:** Use `id_contrato` directly as the MERGE key. No composite construction needed.

### Pitfall 4: SECOP II valor_del_contrato Format Differs From SECOP I
**What goes wrong:** Developer applies SECOP I's `_parse_valor()` (which removes dots as thousands separators) to SECOP II values, causing parse errors or wrong amounts.
**Why it happens:** SECOP I stores values like `"1.500.000"` (dots as thousands separator). SECOP II stores values like `"23300213"` (plain integer string, no separators).
**How to avoid:** For SECOP II, parse `valor_del_contrato` with a simpler cast: `float(str(raw).strip())` without dot removal. Confirm against live data (verified: SECOP II values are plain integers).

### Pitfall 5: SIGEP EntidadPublica Cannot Merge With SECOP's entidad_codigo Constraint
**What goes wrong:** SIGEP has no `codigo_entidad` field. A naive `MERGE (ent:EntidadPublica {codigo_entidad: $codigo})` with a null value will try to create a node with `codigo_entidad: null`, which Neo4j refuses because of the uniqueness constraint.
**Why it happens:** The schema constraint `entidad_codigo` requires `codigo_entidad IS UNIQUE`. Attempting MERGE with a null value raises a constraint violation.
**How to avoid:** For SIGEP entities, use a different MERGE strategy: match by `nombre` property (not `codigo_entidad`) and create with only `nombre` + `fuente` + `ingested_at`. Use `MERGE (ent:EntidadPublica {nombre: $nombre})` as the path for SIGEP-sourced entities. This may create duplicate entities if the name differs slightly from SECOP's name for the same entity — accept this for v1.

### Pitfall 6: SECOP Multas nit_entidad Has Check Digits
**What goes wrong:** Raw `nit_entidad` values like `"890000858-1"` are passed directly to MERGE, creating a node that does not match the same entity's `normalize_nit("890000858-1") = "890000858"` already in the graph.
**Why it happens:** Some records in the Multas dataset include the NIT check digit with a hyphen.
**How to avoid:** Always pass `nit_entidad` through `normalize_nit()` before MERGE. The existing normalizer handles the hyphen-split check digit strip.

### Pitfall 7: SIRI fecha_efectos_juridicos Is DD/MM/YYYY Not ISO8601
**What goes wrong:** Downstream code tries to parse the date as ISO8601 or `$where` filter uses `fecha_efectos_juridicos > 'YYYY-MM-DD'` — the Socrata filter may fail or sort incorrectly.
**Why it happens:** SIRI's date field uses the Colombian administrative format (DD/MM/YYYY) rather than ISO8601.
**How to avoid:** Store `fecha_efectos_juridicos` as a string property. For incremental pagination, sort by `numero_siri` instead of by this date field (numero_siri is a numeric string that sorts stably). For the `$where` incremental filter, prefer `numero_siri > '{last_siri_number}'` if state tracking is per-page, or accept full reloads for SIRI (44K rows is manageable).

### Pitfall 8: Multas documento_contratista Cannot Be Reliably Classified Without Discriminator
**What goes wrong:** Pipeline tries to classify all `documento_contratista` values as cedula or NIT by length alone (e.g., "10 digits = NIT"), misclassifying cedulas that happen to be 10 digits.
**Why it happens:** Colombian cedulas range 6-10 digits; NITs are typically 9-10 digits. The ranges overlap.
**How to avoid:** Use a two-step approach: (1) Check if the normalized value matches an existing `Empresa.nit` or `Persona.cedula` in the graph (via a MATCH before MERGE). (2) If no match, fall back to name-based heuristic (legal suffix detection via `normalize_razon_social`). Document this as a known data quality limitation.

### Pitfall 9: run.py PIPELINES Dict Not Updated
**What goes wrong:** New pipeline classes are implemented but never registered, so `python -m etl.run secop_ii_contratos` fails with "Unknown pipeline."
**Why it happens:** `etl/run.py` has a hardcoded `PIPELINES` dict that must be updated manually.
**How to avoid:** As part of implementing each new pipeline, add it to the `PIPELINES` dict in `run.py`.

---

## Code Examples

### SECOP II Cypher — Three-Pass Pattern

```python
# Source: secop_integrado.py pattern, adapted for SECOP II field names

CYPHER_ENTIDAD_CONTRATO = """
UNWIND $batch AS row

MERGE (ent:EntidadPublica {codigo_entidad: row.codigo_entidad})
ON CREATE SET
    ent.nombre        = row.nombre_entidad,
    ent.nit           = row.nit_entidad,
    ent.departamento  = row.departamento,
    ent.municipio     = row.ciudad,
    ent.sector        = row.sector,
    ent.orden         = row.orden,
    ent.fuente        = row.fuente,
    ent.ingested_at   = datetime()
ON MATCH SET
    ent.nombre        = row.nombre_entidad,
    ent.updated_at    = datetime()

MERGE (c:Contrato {id_contrato: row.id_contrato})
ON CREATE SET
    c.valor           = row.valor_contrato,
    c.objeto          = row.objeto_contrato,
    c.tipo            = row.tipo_contrato,
    c.modalidad       = row.modalidad,
    c.estado          = row.estado_contrato,
    c.fecha_firma     = row.fecha_firma,
    c.fecha_inicio    = row.fecha_inicio,
    c.fecha_fin       = row.fecha_fin,
    c.numero_proceso  = row.proceso_compra,
    c.fuente          = row.fuente,
    c.ingested_at     = datetime(),
    c.url_fuente      = row.url_proceso
ON MATCH SET
    c.estado          = row.estado_contrato,
    c.updated_at      = datetime()

MERGE (ent)-[:ADJUDICO {modalidad: row.modalidad}]->(c)
"""
```

### SIRI Cypher — Two-Pass Pattern (Sancion then Persona)

```python
CYPHER_SANCION = """
UNWIND $batch AS row
MERGE (s:Sancion {id_sancion: row.id_sancion})
ON CREATE SET
    s.tipo_inhabilidad   = row.tipo_inhabilidad,
    s.tipo_sancion       = row.tipo_sancion,
    s.calidad_persona    = row.calidad_persona,
    s.cargo              = row.cargo,
    s.duracion_anos      = row.duracion_anos,
    s.duracion_mes       = row.duracion_mes,
    s.autoridad          = row.autoridad,
    s.fecha_efectos      = row.fecha_efectos,
    s.numero_proceso     = row.numero_proceso,
    s.entidad            = row.entidad_sancionado,
    s.departamento       = row.lugar_hechos_departamento,
    s.municipio          = row.lugar_hechos_municipio,
    s.fuente             = row.fuente,
    s.ingested_at        = datetime()
ON MATCH SET
    s.updated_at         = datetime()
"""

CYPHER_PERSONA_SANCIONADO = """
UNWIND $batch AS row
MERGE (p:Persona {cedula: row.cedula})
ON CREATE SET
    p.nombre        = row.nombre_completo,
    p.fuente        = row.fuente,
    p.ingested_at   = datetime()
ON MATCH SET
    p.updated_at    = datetime()
WITH p, row
MATCH (s:Sancion {id_sancion: row.id_sancion})
MERGE (p)-[:SANCIONADO]->(s)
"""
```

### SIGEP Cypher — name assembly and cedula-keyed Persona

```python
# Note: EntidadPublica MERGE uses nombre, NOT codigo_entidad (SIGEP has no codigo_entidad)
CYPHER_SIGEP = """
UNWIND $batch AS row

MERGE (ent:EntidadPublica {nombre: row.nombre_entidad})
ON CREATE SET
    ent.orden         = row.orden,
    ent.naturaleza    = row.naturaleza,
    ent.fuente        = row.fuente,
    ent.ingested_at   = datetime()
ON MATCH SET
    ent.updated_at    = datetime()

MERGE (p:Persona {cedula: row.cedula})
ON CREATE SET
    p.sexo            = row.sexo,
    p.departamento_nacimiento = row.departamento_nacimiento,
    p.nivel_educativo = row.nivel_educativo,
    p.fuente          = row.fuente,
    p.ingested_at     = datetime()
ON MATCH SET
    p.updated_at      = datetime()

MERGE (p)-[:EMPLEA_EN {
    cargo:             row.cargo,
    nivel_jerarquico:  row.nivel_jerarquico,
    tipo_nombramiento: row.tipo_nombramiento,
    fecha_vinculacion: row.fecha_vinculacion,
    fuente:            row.fuente
}]->(ent)
"""
```

### SIGEP asignacionbasicasalarial parse

```python
def _parse_salario(raw) -> float | None:
    """SIGEP uses commas as thousands separator: '1,440,300' -> 1440300.0"""
    if raw is None:
        return None
    try:
        cleaned = str(raw).replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None
```

### SIRI trailing whitespace strip

```python
cedula_raw = (row.get("numero_identificacion") or "").strip()  # CRITICAL: strip before normalize
cedula = normalize_cedula(cedula_raw)
if not cedula:
    logger.warning("Skipping SIRI row %s — unresolvable cedula", row.get("numero_siri"))
    skipped += 1
    continue
```

### Multas name-based classifier (Claude's discretion)

```python
_EMPRESA_SUFFIXES = {
    "s.a.s", "sas", "s.a", "ltda", "s.c.a", "e.u",
    "union temporal", "consorcio", "asociacion",
}

def classify_contratista_type(nombre: str | None) -> str:
    """Classify Multas contractor as empresa or persona based on name heuristics."""
    if not nombre:
        return "desconocido"
    key = nombre.lower().strip()
    for suffix in _EMPRESA_SUFFIXES:
        if suffix in key:
            return "empresa"
    return "persona"
```

### run.py extension

```python
from etl.sources.secop_ii_contratos import SecopIIContratosPipeline
from etl.sources.sigep_servidores import SigepServidoresPipeline
from etl.sources.siri_sanciones import SiriSancionesPipeline
from etl.sources.secop_multas import SecopMultasPipeline

PIPELINES = {
    "secop_integrado":   SecopIntegradoPipeline,
    "secop_ii_contratos": SecopIIContratosPipeline,
    "sigep_servidores":   SigepServidoresPipeline,
    "siri_sanciones":     SiriSancionesPipeline,
    "secop_multas":       SecopMultasPipeline,
}
```

---

## Schema Changes Required

The existing `infra/neo4j/schema.cypher` constraints are sufficient for Phase 2. No new constraints are needed.

| Constraint | Covers | Status |
|------------|--------|--------|
| `empresa_nit` | Empresa.nit | Exists |
| `persona_cedula` | Persona.cedula | Exists |
| `contrato_id` | Contrato.id_contrato | Exists |
| `proceso_ref` | Proceso.referencia_proceso | Exists (unused in Phase 2) |
| `sancion_id` | Sancion.id_sancion | Exists — used by both SIRI and Multas |
| `entidad_codigo` | EntidadPublica.codigo_entidad | Exists |

**Note:** SIGEP entities MERGE on `nombre` not `codigo_entidad`. This is a deliberate trade-off — SIGEP-sourced EntidadPublica nodes may duplicate SECOP-sourced ones if names differ. No new constraint is needed; the existing `entidad_codigo` constraint will not be triggered when SIGEP entities are created without that field.

**Recommended addition (optional):** An index on `EntidadPublica.nombre` would speed up SIGEP's name-based MERGE. Add to `schema.cypher`:
```cypher
CREATE INDEX entidad_nombre IF NOT EXISTS
  FOR (e:EntidadPublica) ON (e.nombre);
```

---

## Environment Availability

> Step 2.6: Applicable — pipelines depend on the Socrata API and Neo4j.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| datos.gov.co Socrata API | All 4 pipelines | Confirmed | SODA v2.1 | No fallback — required data source |
| Neo4j 5.26 LTS | All writes | Assumed present (Phase 1) | 5.26 LTS | — |
| Python 3.12 | All pipelines | Assumed present (Phase 1) | 3.12 | — |
| Socrata App Token | Rate limit bypass | Optional | — | Works without; rate-limited to ~1 req/s |

**Socrata API field name stability:** Field names with accents (e.g., `fecha_de_vinculaci_n`, `modalidad_de_contrataci_n`) are well-established gotchas in the SECOP/SIGEP ecosystem. The Socrata API transcodes these consistently. Use the exact field names verified from live API responses documented above.

---

## Cross-Source Entity Linking (ETL-06)

Entity linking happens automatically when:
1. A `Persona` with `cedula = "12345678"` is created by SECOP II (contractor)
2. Later, SIGEP runs and merges `Persona {cedula: "12345678"}` — the MERGE hits the existing node and adds employment properties
3. SIRI runs and merges `Persona {cedula: "12345678"}` — the MERGE hits the same node and creates a `[:SANCIONADO]->(:Sancion)` relationship

**No separate ETL-06 pipeline is needed.** The graph becomes linked as each pipeline runs in order. The result is:

```
(:Persona {cedula: "12345678"})
  -[:EJECUTA]->(:Contrato)             # from SECOP II
  -[:EMPLEA_EN]->(:EntidadPublica)     # from SIGEP
  -[:SANCIONADO]->(:Sancion)           # from SIRI
```

This is the core value of the graph model — the links emerge from MERGE rather than a JOIN.

**ETL-06 verification query:**
```cypher
MATCH (p:Persona)
WHERE (p)-[:EJECUTA]->() AND (p)-[:SANCIONADO]->()
RETURN p.cedula, count(*) AS linked_count
LIMIT 10
```
This should return non-zero results after all pipelines have run, confirming cross-source linking works.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| sodapy library (sync) | httpx (async) | Phase 1 already uses httpx |
| Pandas for ETL | Polars | Phase 1 already uses Polars |
| Manual constraint creation | verify_constraints() at startup | Phase 1 already enforces this |

No changes to technology approach needed for Phase 2.

---

## Open Questions

1. **SIGEP EntidadPublica merge strategy**
   - What we know: SIGEP has no `codigo_entidad`; the existing constraint requires it; MERGE on `nombre` creates unindexed-by-constraint nodes
   - What's unclear: Will name-based MERGE for SIGEP entities cause enough duplicates to pollute graph traversals in Phase 3?
   - Recommendation: Proceed with `MERGE (ent:EntidadPublica {nombre: $nombre})` for SIGEP. Add `CREATE INDEX entidad_nombre IF NOT EXISTS FOR (e:EntidadPublica) ON (e.nombre)` to schema.cypher. Accept duplicate entities in v1; plan a reconciliation Cypher script for Phase 3 when SECOP data is available to match on NIT.

2. **Multas documento_contratista classification confidence**
   - What we know: No discriminator field; both cedulas and NITs appear; name heuristics can classify most cases
   - What's unclear: What % of the 1,703 records will be misclassified?
   - Recommendation: Given the small dataset size (1,703 rows), a manual review pass after the first load is feasible. Log all "desconocido" and "heuristic" classifications with counts. Accept the imprecision for v1.

3. **SIRI incremental pagination via DD/MM/YYYY dates**
   - What we know: `fecha_efectos_juridicos` is DD/MM/YYYY, not ISO8601; Socrata `$where` date filters expect ISO8601
   - What's unclear: Does Socrata accept `fecha_efectos_juridicos > '2020-01-01'` even for DD/MM/YYYY fields?
   - Recommendation: Use `numero_siri > '{last_numero_siri}'` for incremental filtering instead. Store `last_numero_siri` as a string in state. This avoids the date format problem entirely. For the initial full load, sort by `numero_siri ASC`.

---

## Sources

### Primary (HIGH confidence)
- Live Socrata API — `https://www.datos.gov.co/resource/jbjy-vk9h.json` — field names and formats verified against actual API response (2026-04-09)
- Live Socrata API — `https://www.datos.gov.co/resource/2jzx-383z.json` — field names, nombre field behavior, date format verified (2026-04-09)
- Live Socrata API — `https://www.datos.gov.co/resource/iaeu-rcn6.json` — field names, trailing whitespace, calidad_persona/tipo_identificacion combos, date format verified (2026-04-09)
- Live Socrata API — `https://www.datos.gov.co/resource/4n4q-k399.json` — field names, nit_entidad check digit format verified (2026-04-09)
- `etl/sources/secop_integrado.py` — reference implementation verified by reading source
- `etl/normalizers/common.py` — normalization functions verified by reading source
- `etl/loaders/neo4j_loader.py` — REQUIRED_CONSTRAINTS set verified by reading source
- `infra/neo4j/schema.cypher` — all existing constraints verified by reading source
- `.planning/research/PITFALLS.md` — domain pitfalls (researched Phase 1, author: planning AI)

### Secondary (MEDIUM confidence)
- Dataset row counts via Socrata `$select=COUNT(*)` (2026-04-09) — counts may shift as data updates daily
- `calidad_persona` enum values via Socrata `$group` query — verified across dataset; no NIT/empresa records found, but absence of evidence is not evidence of absence for edge cases

### Tertiary (LOW confidence)
- Multas classifier heuristic (name-based) — based on observed data patterns in 10-record sample; not validated against full 1,703 records

---

## Metadata

**Confidence breakdown:**
- SECOP II field map: HIGH — verified from live API, 3+ record samples, all key fields confirmed
- SIGEP field map: HIGH — verified; the nombre=ID discovery is confirmed across multiple offsets
- SIRI field map: HIGH — verified; trailing whitespace and DD/MM/YYYY date format confirmed
- Multas field map: HIGH — verified; no-discriminator problem is a real limitation, not a gap in research
- Cross-source linking approach: HIGH — follows directly from Neo4j MERGE semantics, validated by Phase 1 architecture
- SIGEP EntidadPublica merge: MEDIUM — workaround is reasonable but will create some duplicates
- Multas classifier: LOW — heuristic approach; works for most cases but not guaranteed

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (Socrata field names are stable; API responses unlikely to change)
