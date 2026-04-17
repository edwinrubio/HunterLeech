"""
SIRI Sanciones Disciplinarias (iaeu-rcn6) ETL pipeline.

Loads Procuraduria disciplinary sanctions data from datos.gov.co Socrata API into Neo4j.
Creates: :Sancion, :Persona nodes
Creates: (Persona)-[:SANCIONADO]->(Sancion)

Key design decisions:
- id_sancion = numero_siri (globally unique per RESEARCH.md)
- Persona MERGE key = cedula (from numero_identificacion after strip + normalize_cedula())
- CRITICAL pitfall: numero_identificacion arrives padded with trailing whitespace
  (e.g. "7534386        "). MUST call .strip() BEFORE normalize_cedula().
- fecha_efectos_juridicos stored as string (DD/MM/YYYY format — NOT parsed to ISO).
  Sorting uses numero_siri not the date (DD/MM/YYYY sorts lexicographically incorrect).
- Persona.nombre set ON CREATE only (not ON MATCH) to preserve SECOP-sourced names.
- Two-pass load: Sancion nodes first, then Persona + SANCIONADO relationship.
- SIRI is 44K rows — full reload accepted (no incremental where-clause filtering).

Provenance (ETL-07): every node carries fuente='iaeu-rcn6', ingested_at=datetime()
Idempotence (ETL-08): all writes use MERGE ON CREATE / ON MATCH — re-run safe
Entity linking (ETL-06): MERGE on cedula automatically links Persona nodes already
  existing from SECOP or SIGEP sources.
"""

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
import polars as pl

from etl.base import BasePipeline
from etl.config import etl_config
from etl.loaders.neo4j_loader import Neo4jLoader
from etl.normalizers.common import normalize_cedula
from etl.state import RunState

logger = logging.getLogger(__name__)

DATASET_ID = "iaeu-rcn6"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
FUENTE = DATASET_ID  # provenance tag on every node


# ---------------------------------------------------------------------------
# Cypher — two passes (Anti-Pattern 1 compliance: separate node and rel MERGEs)
# ---------------------------------------------------------------------------

CYPHER_SANCION = """
UNWIND $batch AS row
MERGE (s:Sancion {id_sancion: row.id_sancion})
ON CREATE SET
    s.tipo_inhabilidad   = row.tipo_inhabilidad,
    s.tipo_sancion       = row.tipo_sancion,
    s.calidad_persona    = row.calidad_persona,
    s.cargo              = row.cargo_sancionado,
    s.duracion_anos      = row.duracion_anos,
    s.duracion_mes       = row.duracion_mes,
    s.duracion_dias      = row.duracion_dias,
    s.providencia        = row.providencia,
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


class SiriSancionesPipeline(BasePipeline):
    name = DATASET_ID
    label = "SIRI Sanciones Disciplinarias"

    async def extract(self, state: RunState) -> AsyncGenerator[pl.DataFrame, None]:
        """
        Paginate SIRI Sanciones dataset via Socrata SODA API.
        Sort field: numero_siri ASC (not fecha_efectos_juridicos — DD/MM/YYYY sorts wrong).
        Full reload on each run — dataset is small (~44K rows), no incremental filter.
        """
        params: dict = {
            "$limit": etl_config.page_size,
            "$order": "numero_siri ASC",
        }

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
        Normalize SIRI rows into dicts ready for Neo4j MERGE.
        Skips records with unresolvable keys (logs skip reason with numero_siri).

        Field mapping notes:
        - numero_siri -> id_sancion (MERGE key for Sancion)
        - numero_identificacion -> cedula (CRITICAL: strip() BEFORE normalize_cedula())
        - fecha_efectos_juridicos stored as DD/MM/YYYY string — NO ISO conversion
        - nombre_completo assembled from 4 name fields (skipping None and '/' placeholders)
        """
        records = []
        ingested_at = datetime.now(timezone.utc).isoformat()
        skipped = 0

        for row in df.to_dicts():
            # Mandatory: Sancion MERGE key
            numero_siri = (row.get("numero_siri") or "").strip()
            if not numero_siri:
                logger.warning("Skipping SIRI row — missing numero_siri")
                skipped += 1
                continue

            # CRITICAL pitfall: strip() BEFORE normalize_cedula()
            # numero_identificacion arrives with trailing whitespace padding
            cedula_raw = (row.get("numero_identificacion") or "").strip()
            cedula = normalize_cedula(cedula_raw)
            if not cedula:
                logger.warning(
                    "Skipping SIRI row %s — normalize_cedula(%r) returned None",
                    numero_siri,
                    cedula_raw,
                )
                skipped += 1
                continue

            # Assemble nombre_completo from 4 name parts (skipping None and '/' placeholders)
            parts = [
                row.get("primer_nombre"),
                row.get("segundo_nombre"),
                row.get("primer_apellido"),
                row.get("segundo_apellido"),
            ]
            nombre_completo = " ".join(
                p.strip() for p in parts if p and p.strip() and "/" not in p
            )

            record = {
                # Sancion fields (id_sancion is the MERGE key)
                "id_sancion": numero_siri,
                "tipo_inhabilidad": row.get("tipo_inhabilidad"),
                "tipo_sancion": row.get("sanciones"),
                "calidad_persona": row.get("calidad_persona"),
                "cargo_sancionado": row.get("cargo"),
                "duracion_anos": row.get("duracion_anos"),
                "duracion_mes": row.get("duracion_mes"),
                "duracion_dias": row.get("duracion_dias"),
                "providencia": row.get("providencia"),
                "autoridad": row.get("autoridad"),
                # DD/MM/YYYY stored as string — no ISO parse (pitfall 7)
                "fecha_efectos": row.get("fecha_efectos_juridicos"),
                "numero_proceso": row.get("numero_proceso"),
                "entidad_sancionado": row.get("entidad_sancionado"),
                "lugar_hechos_departamento": row.get("lugar_hechos_departamento"),
                "lugar_hechos_municipio": row.get("lugar_hechos_municipio"),
                # Persona fields (cedula is the MERGE key)
                "cedula": cedula,
                "nombre_completo": nombre_completo,
                # Provenance (ETL-07)
                "fuente": FUENTE,
                "ingested_at": ingested_at,
            }
            records.append(record)

        if skipped:
            logger.info("Skipped %d SIRI records with missing required keys", skipped)

        return records

    def get_cypher(self) -> str:
        # Satisfies BasePipeline abstract method; not used directly since load() is overridden.
        return CYPHER_SANCION

    async def load(self, records: list[dict], loader: Neo4jLoader) -> int:
        """
        Override base load to execute two separate MERGE passes:
        1. Sancion nodes (all records)
        2. Persona nodes + SANCIONADO relationship (all records with valid cedula)
        """
        total = 0
        total += await loader.merge_batch(records, CYPHER_SANCION)
        total += await loader.merge_batch(records, CYPHER_PERSONA_SANCIONADO)
        return total
