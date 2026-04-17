# Field Privacy Classification: SECOP Integrado (rpmr-utcd)

**Status:** Authoritative — must be reviewed before any new field is stored in Neo4j  
**Legal framework:** Ley 1581/2012 (Habeas Data) + Ley 1712/2014 (Transparencia)  
**Dataset:** SECOP Integrado — ID `rpmr-utcd` — datos.gov.co  
**Classified:** 2026-04-09  
**Scope:** All 22 fields present in the live API response as of 2026-04-09

---

## Classification Tiers (Ley 1581/2012)

| Tier | Definition | Example |
|------|------------|---------|
| **PUBLICA** | Freely accessible; disclosable to any person without restriction | Contract value, entity name, contract dates |
| **SEMIPRIVADA** | Of interest to a specific community/sector; limited disclosure context required | Contractor NIT when contractor is a natural person |
| **PRIVADA** | Intimate; only relevant to the owner; requires explicit authorization | Home address, personal phone number |
| **SENSIBLE** | Can cause discrimination if disclosed (health, political views, sexual orientation) | Medical records, union membership |

---

## SECOP Integrado Field Inventory

| # | Field Name (API) | Display Name (ES) | Type | Classification | Rationale |
|---|-----------------|-------------------|------|---------------|-----------|
| 1 | `nivel_entidad` | Nivel Entidad | text | PUBLICA | Organizational level of contracting entity — public record |
| 2 | `codigo_entidad_en_secop` | Codigo Entidad en SECOP | text | PUBLICA | Public identifier assigned by Colombia Compra Eficiente |
| 3 | `nombre_de_la_entidad` | Nombre de la Entidad | text | PUBLICA | Full legal name of public entity — required by Ley 80/1993 |
| 4 | `nit_de_la_entidad` | NIT de la Entidad | text | PUBLICA | NIT of a public contracting entity is public per Ley 1712/2014 |
| 5 | `departamento_entidad` | Departamento Entidad | text | PUBLICA | Geographic — public administrative record |
| 6 | `municipio_entidad` | Municipio Entidad | text | PUBLICA | Geographic — public administrative record |
| 7 | `estado_del_proceso` | Estado del Proceso | text | PUBLICA | Contract lifecycle status — public per transparency law |
| 8 | `modalidad_de_contrataci_n` | Modalidad de Contratacion | text | PUBLICA | Procurement modality — public record per Ley 80/1993 |
| 9 | `objeto_a_contratar` | Objeto del Contrato | text | PUBLICA | Contract scope — required public disclosure |
| 10 | `objeto_del_proceso` | Objeto del Proceso | text | PUBLICA | Process object — public |
| 11 | `tipo_de_contrato` | Tipo de Contrato | text | PUBLICA | Contract type — public classification |
| 12 | `fecha_de_firma_del_contrato` | Fecha de Firma del Contrato | date | PUBLICA | Public contracting date — required disclosure |
| 13 | `fecha_inicio_ejecuci_n` | Fecha Inicio Ejecucion | date | PUBLICA | Execution start date — public |
| 14 | `fecha_fin_ejecuci_n` | Fecha Fin Ejecucion | date | PUBLICA | Execution end date — public |
| 15 | `numero_del_contrato` | Numero del Contrato | text | PUBLICA | Public contract identifier |
| 16 | `numero_de_proceso` | Numero de Proceso | text | PUBLICA | Public process reference |
| 17 | `valor_contrato` | Valor del Contrato (COP) | number | PUBLICA | Contract value — public per transparency law |
| 18 | `nom_raz_social_contratista` | Razon Social del Contratista | text | **SEMIPRIVADA** | Legal entity name: PUBLICA when acting as contractor (Art. 26 Ley 1581 + Ley 1712/2014). Natural person name: SEMIPRIVADA — show in contract context only, not for unrelated profiling |
| 19 | `url_contrato` | URL Contrato SECOP | text | PUBLICA | Link to the public SECOP record |
| 20 | `origen` | Origen (SECOPI / SECOPII) | text | PUBLICA | Dataset provenance flag — internal metadata |
| 21 | `tipo_documento_proveedor` | Tipo Documento Proveedor | text | PUBLICA | Document type classifier (NIT, cedula) — public |
| 22 | `documento_proveedor` | Documento del Proveedor | text | **SEMIPRIVADA** | NIT of legal entity: PUBLICA in contracting role. Cedula of natural person (when `tipo_documento_proveedor = "Nit de Persona Natural"` or cedula type): SEMIPRIVADA — store but apply PUBLIC_MODE filter |

---

## Implementation Rules for SEMIPRIVADA Fields

### `nom_raz_social_contratista` (field 18)

- **Store:** Always store in Neo4j as `razon_social` on `:Empresa` or `nombre` on `:Persona`
- **PUBLIC_MODE=true:** Display in contract detail context. Do NOT include in search autocomplete for natural person names.
- **PUBLIC_MODE=false:** No restriction — available for investigative use

### `documento_proveedor` (field 22)

- **When `tipo_documento_proveedor` is `"Nit"` (legal entity):** Treat as PUBLICA. Use as MERGE key for `:Empresa {nit: normalized_value}`.
- **When `tipo_documento_proveedor` is `"Nit de Persona Natural"` or any cedula type:** Treat as SEMIPRIVADA. Use as MERGE key for `:Persona {cedula: normalized_value}`.
  - **PUBLIC_MODE=true:** Do not expose in free-text search results. Only show in specific contract context where the person is named as contractor.
  - **PUBLIC_MODE=false:** Available for cross-source linking (SIGEP, SIRI).

---

## PRIVADA / SENSIBLE Assessment

**Conclusion: No field in SECOP Integrado (rpmr-utcd) is classified PRIVADA or SENSIBLE.**

The dataset does not contain: home addresses, personal phone numbers, health data, political affiliation, religious beliefs, or any other category covered under the SENSIBLE or PRIVADA tiers of Ley 1581/2012.

All 22 fields may be ingested. SEMIPRIVADA fields require context-aware exposure controls (see above).

---

## Entity Resolution Rules (INFRA-03)

These rules apply to all ETL pipelines, not just SECOP Integrado.

### NIT Normalization

All NIT values must pass through `etl.normalizers.common.normalize_nit()` before use as a MERGE key.

Canonical form: digits only, no leading zeros, no check digit (check digit follows the hyphen separator).

| Raw Format | Canonical |
|-----------|-----------|
| "890399010-4" | "890399010" |
| "0890399010" | "890399010" |
| "890.399.010" | "890399010" |
| "N/A" | None — SKIP |
| "" | None — SKIP |

**Null policy:** If normalize_nit() returns None, DO NOT create an `:Empresa` or `:Persona` node. Log the skip. Never MERGE with an empty string or placeholder.

### Cedula Normalization

All cedula values must pass through `etl.normalizers.common.normalize_cedula()`. Same rules as NIT (cedulas have no check digit).

### Empresa vs Persona Distinction

Use `etl.normalizers.common.classify_proveedor_type(documento, tipo_documento_proveedor)`:
- Returns `"empresa"` → MERGE as `:Empresa {nit: normalize_nit(documento)}`
- Returns `"persona"` → MERGE as `:Persona {cedula: normalize_cedula(documento)}`
- Returns `"desconocido"` → Skip MERGE, log record ID for review

### Contrato Composite Key

MERGE key for `:Contrato`: `numero_del_contrato + "_" + origen`

Rationale: The same contract number can appear in both SECOPI and SECOPII origin records during the 2015-2018 transition period. Scoping by origin prevents false merges. Phase 2 will add a cross-origin deduplication pass.

---

## Review Checklist

Before adding any new dataset to the ETL pipeline:

- [ ] Fetch live schema from `https://www.datos.gov.co/resource/{DATASET_ID}.json?$limit=1`
- [ ] List all fields present in the API response
- [ ] Classify each field against the four tiers above
- [ ] Document any SEMIPRIVADA or higher fields and their implementation rules
- [ ] Add the new classification table to this document
- [ ] Get sign-off before writing ingestion code

---

*Classification methodology: Ley 1581/2012 (Habeas Data, 2012), Ley 1712/2014 (Transparencia y del Derecho de Acceso a la Informacion Publica), and Colombia Compra Eficiente Manual SECOP II 2024.*
