"""
SECOP Multas y Sanciones (4n4q-k399) ETL pipeline.

Loads SECOP sanctions/fines data from datos.gov.co Socrata API into Neo4j.
Creates: :EntidadPublica, :Sancion, :Empresa/:Persona nodes
Creates:
  (EntidadPublica)-[:IMPUSO]->(Sancion)
  (Empresa)-[:MULTADO]->(Sancion)
  (Persona)-[:MULTADO]->(Sancion)

Key design decisions:
- id_sancion = composite: f"{normalize_nit(nit_entidad) or ''}_{numero_de_resolucion}_{doc_clean or doc_raw}"
  No globally unique identifier exists; composite prevents false merges.
- Contratista classification uses name-based heuristics (classify_contratista_type()).
  Multas dataset has NO tipodocproveedor discriminator field (pitfall 8).
- nit_entidad may have check digit "890000858-1" — normalize_nit() strips it (pitfall 6).
- EntidadPublica MERGE on nit (Multas provides nit_entidad but not codigo_entidad).
  This node will not collide with the codigo_entidad unique constraint (different property).
- Three-pass load: Sancion+Entidad, Empresa+MULTADO, Persona+MULTADO.

Provenance (ETL-07): every node carries fuente='4n4q-k399', ingested_at=datetime()
Idempotence (ETL-08): all writes use MERGE ON CREATE / ON MATCH — re-run safe
Entity linking (ETL-06): MERGE on normalized NIT/cedula links Empresa/Persona nodes
  already existing from SECOP Integrado or SECOP II sources.
"""

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
import polars as pl

from etl.base import BasePipeline
from etl.config import etl_config
from etl.loaders.neo4j_loader import Neo4jLoader
from etl.normalizers.common import normalize_nit
from etl.state import RunState

logger = logging.getLogger(__name__)

DATASET_ID = "4n4q-k399"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
FUENTE = DATASET_ID  # provenance tag on every node


# ---------------------------------------------------------------------------
# Name-based contratista classifier (no doc type discriminator in Multas)
# ---------------------------------------------------------------------------

_EMPRESA_SUFFIXES = {
    "s.a.s", "sas", "s.a", "ltda", "s.c.a", "e.u",
    "union temporal", "consorcio", "asociacion",
}


def classify_contratista_type(nombre: str | None) -> str:
    """Classify Multas contractor as empresa or persona based on name heuristics.

    No document-type discriminator exists in this dataset (pitfall 8).
    Returns 'empresa', 'persona', or 'desconocido'.
    """
    if not nombre:
        return "desconocido"
    key = nombre.lower().strip()
    for suffix in _EMPRESA_SUFFIXES:
        if suffix in key:
            return "empresa"
    return "persona"


# ---------------------------------------------------------------------------
# Cypher — three passes (ARCHITECTURE Anti-Pattern 1 compliance)
# ---------------------------------------------------------------------------

CYPHER_SANCION_ENTIDAD = """
UNWIND $batch AS row

MERGE (ent:EntidadPublica {nit: row.nit_entidad})
ON CREATE SET
    ent.nombre      = row.nombre_entidad,
    ent.nivel       = row.nivel,
    ent.orden       = row.orden,
    ent.municipio   = row.municipio,
    ent.fuente      = row.fuente,
    ent.ingested_at = datetime()
ON MATCH SET
    ent.updated_at  = datetime()

MERGE (s:Sancion {id_sancion: row.id_sancion})
ON CREATE SET
    s.numero_resolucion  = row.numero_resolucion,
    s.numero_contrato    = row.numero_contrato,
    s.valor              = row.valor_sancion,
    s.fecha_publicacion  = row.fecha_publicacion,
    s.fecha_firmeza      = row.fecha_firmeza,
    s.fecha_cargue       = row.fecha_cargue,
    s.url_fuente         = row.url_fuente,
    s.fuente             = row.fuente,
    s.ingested_at        = datetime()
ON MATCH SET
    s.updated_at         = datetime()

MERGE (ent)-[:IMPUSO]->(s)
"""

CYPHER_EMPRESA_MULTADO = """
UNWIND $batch AS row
MERGE (e:Empresa {nit: row.nit_contratista})
ON CREATE SET
    e.razon_social  = row.nombre_contratista,
    e.fuente        = row.fuente,
    e.ingested_at   = datetime()
ON MATCH SET
    e.updated_at    = datetime()
WITH e, row
MATCH (s:Sancion {id_sancion: row.id_sancion})
MERGE (e)-[:MULTADO]->(s)
"""

CYPHER_PERSONA_MULTADO = """
UNWIND $batch AS row
MERGE (p:Persona {cedula: row.cedula_contratista})
ON CREATE SET
    p.nombre        = row.nombre_contratista,
    p.fuente        = row.fuente,
    p.ingested_at   = datetime()
ON MATCH SET
    p.updated_at    = datetime()
WITH p, row
MATCH (s:Sancion {id_sancion: row.id_sancion})
MERGE (p)-[:MULTADO]->(s)
"""


def _parse_valor(raw) -> float | None:
    """Parse sancion value as float (plain integer string in Multas dataset)."""
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except (ValueError, TypeError):
        return None


class SecopMultasPipeline(BasePipeline):
    name = DATASET_ID
    label = "SECOP Multas y Sanciones"

    async def extract(self, state: RunState) -> AsyncGenerator[pl.DataFrame, None]:
        """
        Paginate SECOP Multas dataset via Socrata SODA API.
        Sort field: fecha_de_publicacion ASC.
        For incremental runs, filters by fecha_de_publicacion > last_run_at.
        Dataset is only ~1,703 rows — single page likely, but paginate for correctness.
        """
        params: dict = {
            "$limit": etl_config.page_size,
            "$order": "fecha_de_publicacion ASC",
        }

        last_run_at = state.get("last_run_at")
        if last_run_at:
            params["$where"] = f"fecha_de_publicacion > '{last_run_at}'"

        headers = {}
        if etl_config.socrata_app_token:
            headers["X-App-Token"] = etl_config.socrata_app_token

        offset = state.get("last_page", 0) * etl_config.page_size
        page = state.get("last_page", 0)

        async with httpx.AsyncClient(timeout=etl_config.http_timeout) as client:
            while True:
                params["$offset"] = offset
                response = await client.get(BASE_URL, params=params, headers=headers)
                response.raise_for_status()
                rows = response.json()

                if not rows:
                    break

                df = pl.DataFrame(rows, infer_schema_length=None)
                state["last_page"] = page
                yield df

                if len(rows) < etl_config.page_size:
                    break

                offset += etl_config.page_size
                page += 1

    def transform(self, df: pl.DataFrame) -> list[dict]:
        """
        Normalize Multas rows into dicts ready for Neo4j MERGE.
        Skips records with missing numero_de_resolucion (can't build stable id_sancion).

        Field mapping notes:
        - id_sancion: composite from nit_entidad + numero_de_resolucion + doc_clean
        - nit_entidad: normalize_nit() strips check digit (pitfall 6)
        - documento_contratista: normalize_nit() on both empresa and persona paths
        - contratista_type: name-based heuristics (no tipodocproveedor available)
        """
        records = []
        ingested_at = datetime.now(timezone.utc).isoformat()
        skipped = 0

        for row in df.to_dicts():
            # Mandatory: need resolucion to build stable id_sancion
            numero_de_resolucion = (row.get("numero_de_resolucion") or "").strip()
            if not numero_de_resolucion:
                logger.warning("Skipping Multas row — missing numero_de_resolucion")
                skipped += 1
                continue

            # NIT normalization — strip check digit (pitfall 6)
            nit_entidad_raw = row.get("nit_entidad")
            nit_entidad = normalize_nit(nit_entidad_raw)

            # Contractor document normalization
            doc_raw = (row.get("documento_contratista") or "").strip()
            doc_clean = normalize_nit(doc_raw)  # returns None for non-numeric

            # Composite id_sancion (no globally unique key in this dataset)
            id_sancion = f"{nit_entidad or ''}_{numero_de_resolucion}_{doc_clean or doc_raw}"

            # Classify contratista by name (no discriminator field available)
            nombre_contratista = row.get("nombre_contratista")
            contratista_type = classify_contratista_type(nombre_contratista)

            record = {
                # EntidadPublica fields (MERGE on nit — no codigo_entidad in Multas)
                "nit_entidad": nit_entidad,
                "nombre_entidad": (row.get("nombre_entidad") or "").strip(),
                "nivel": row.get("nivel"),
                "orden": row.get("orden"),
                "municipio": row.get("municipio"),
                # Sancion fields (id_sancion is the MERGE key)
                "id_sancion": id_sancion,
                "numero_resolucion": numero_de_resolucion,
                "numero_contrato": row.get("numero_de_contrato"),
                "valor_sancion": _parse_valor(row.get("valor_sancion")),
                "fecha_publicacion": row.get("fecha_de_publicacion"),
                "fecha_firmeza": row.get("fecha_de_firmeza"),
                "fecha_cargue": row.get("fecha_de_cargue"),
                "url_fuente": row.get("ruta_de_proceso"),
                # Contractor fields
                "nombre_contratista": nombre_contratista,
                "contratista_type": contratista_type,
                "nit_contratista": doc_clean if contratista_type == "empresa" else None,
                "cedula_contratista": doc_clean if contratista_type == "persona" else None,
                # Provenance (ETL-07)
                "fuente": FUENTE,
                "ingested_at": ingested_at,
            }
            records.append(record)

        if skipped:
            logger.info("Skipped %d Multas records with missing required keys", skipped)

        return records

    def get_cypher(self) -> str:
        # Satisfies BasePipeline abstract method; not used directly since load() is overridden.
        return CYPHER_SANCION_ENTIDAD

    async def load(self, records: list[dict], loader: Neo4jLoader) -> int:
        """
        Override base load to execute three separate MERGE passes:
        1. EntidadPublica + Sancion + IMPUSO relationship (all records with nit_entidad)
        2. Empresa + MULTADO relationship (empresa records with valid nit_contratista)
        3. Persona + MULTADO relationship (persona records with valid cedula_contratista)
        """
        total = 0

        # Pass 1: All records — entities and sanctions (filter: nit_entidad must not be None)
        total += await loader.merge_batch(records, CYPHER_SANCION_ENTIDAD)

        # Pass 2: Empresa contractors (name-classified as empresa, valid normalized NIT)
        empresa_records = [
            r for r in records
            if r["contratista_type"] == "empresa" and r["nit_contratista"] is not None
        ]
        total += await loader.merge_batch(empresa_records, CYPHER_EMPRESA_MULTADO)
        if empresa_records:
            logger.info("Merged %d Empresa MULTADO records", len(empresa_records))

        # Pass 3: Persona contractors (name-classified as persona, valid normalized cedula)
        persona_records = [
            r for r in records
            if r["contratista_type"] == "persona" and r["cedula_contratista"] is not None
        ]
        total += await loader.merge_batch(persona_records, CYPHER_PERSONA_MULTADO)
        if persona_records:
            logger.info("Merged %d Persona MULTADO records", len(persona_records))

        desconocido_count = sum(1 for r in records if r["contratista_type"] == "desconocido")
        if desconocido_count:
            logger.warning(
                "Skipped %d Multas records with unknown contratista type (no contractor node created)",
                desconocido_count,
            )

        return total
