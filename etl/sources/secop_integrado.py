"""
SECOP Integrado (rpmr-utcd) ETL pipeline.

Loads public contracting data from datos.gov.co Socrata API into Neo4j.
Creates: :EntidadPublica, :Empresa/:Persona (contractor), :Contrato nodes
Creates: (EntidadPublica)-[:ADJUDICO]->(Contrato), (Empresa|Persona)-[:EJECUTA]->(Contrato)

Key design decisions (see docs/privacy/field_classification.md):
- Contrato MERGE key = numero_del_contrato + "_" + origen (composite — avoids false
  merges between SECOPI and SECOPII records during 2015-2018 transition period)
- documento_proveedor where tipo is "Nit de Persona Natural" -> :Persona node (SEMIPRIVADA)
- Nodes with unresolvable NIT/cedula are SKIPPED — never merged with null key
- All identifier normalization delegates to etl.normalizers.common — no inline logic

Provenance (ETL-07): every node carries fuente='rpmr-utcd', ingested_at=datetime(), url_fuente
Idempotence (ETL-08): all writes use MERGE ON CREATE / ON MATCH — re-run safe
"""

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
import polars as pl

from etl.base import BasePipeline
from etl.config import etl_config
from etl.loaders.neo4j_loader import Neo4jLoader
from etl.normalizers.common import (
    classify_proveedor_type,
    normalize_nit,
    normalize_razon_social,
)
from etl.state import RunState

logger = logging.getLogger(__name__)

DATASET_ID = "rpmr-utcd"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
FUENTE = DATASET_ID  # provenance tag on every node


# ---------------------------------------------------------------------------
# Cypher — separated into node MERGEs then relationship MERGE (ARCHITECTURE Anti-Pattern 1)
# ---------------------------------------------------------------------------

CYPHER_ENTIDAD_CONTRATO = """
UNWIND $batch AS row

// 1. MERGE EntidadPublica node
MERGE (ent:EntidadPublica {codigo_entidad: row.codigo_entidad})
ON CREATE SET
    ent.nombre        = row.nombre_entidad,
    ent.nivel         = row.nivel_entidad,
    ent.nit           = row.nit_entidad,
    ent.departamento  = row.departamento_entidad,
    ent.municipio     = row.municipio_entidad,
    ent.fuente        = row.fuente,
    ent.ingested_at   = datetime()
ON MATCH SET
    ent.nombre        = row.nombre_entidad,
    ent.updated_at    = datetime()

// 2. MERGE Contrato node (composite key: numero + origen)
MERGE (c:Contrato {id_contrato: row.id_contrato})
ON CREATE SET
    c.valor           = row.valor_contrato,
    c.objeto          = row.objeto_contrato,
    c.tipo            = row.tipo_contrato,
    c.modalidad       = row.modalidad,
    c.estado          = row.estado_proceso,
    c.fecha_firma     = row.fecha_firma,
    c.fecha_inicio    = row.fecha_inicio,
    c.fecha_fin       = row.fecha_fin,
    c.numero_proceso  = row.numero_proceso,
    c.origen          = row.origen,
    c.fuente          = row.fuente,
    c.ingested_at     = datetime(),
    c.url_fuente      = row.url_contrato
ON MATCH SET
    c.estado          = row.estado_proceso,
    c.updated_at      = datetime()

// 3. MERGE ADJUDICO relationship (entity -> contract)
MERGE (ent)-[:ADJUDICO {modalidad: row.modalidad}]->(c)
"""

CYPHER_EMPRESA_EJECUTA = """
UNWIND $batch AS row
MERGE (e:Empresa {nit: row.nit_contratista})
ON CREATE SET
    e.razon_social    = row.razon_social,
    e.fuente          = row.fuente,
    e.ingested_at     = datetime()
ON MATCH SET
    e.razon_social    = row.razon_social,
    e.updated_at      = datetime()
WITH e, row
MATCH (c:Contrato {id_contrato: row.id_contrato})
MERGE (e)-[:EJECUTA]->(c)
"""

CYPHER_PERSONA_EJECUTA = """
UNWIND $batch AS row
MERGE (p:Persona {cedula: row.cedula_contratista})
ON CREATE SET
    p.nombre          = row.razon_social,
    p.fuente          = row.fuente,
    p.ingested_at     = datetime()
ON MATCH SET
    p.nombre          = row.razon_social,
    p.updated_at      = datetime()
WITH p, row
MATCH (c:Contrato {id_contrato: row.id_contrato})
MERGE (p)-[:EJECUTA]->(c)
"""


class SecopIntegradoPipeline(BasePipeline):
    name = DATASET_ID
    label = "SECOP Integrado"

    async def extract(self, state: RunState) -> AsyncGenerator[pl.DataFrame, None]:
        """
        Paginate SECOP Integrado dataset via Socrata SODA API.
        Uses stable sort on fecha_de_firma_del_contrato to prevent offset drift (Pitfall 4).
        For incremental runs, filters by fecha_de_firma_del_contrato > last_run_at.
        """
        params: dict = {
            "$limit": etl_config.page_size,
            "$order": "fecha_de_firma_del_contrato ASC",
        }

        last_run_at = state.get("last_run_at")
        if last_run_at:
            params["$where"] = f"fecha_de_firma_del_contrato > '{last_run_at}'"

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
        Normalize SECOP Integrado rows into dicts ready for Neo4j MERGE.
        Skips records with unresolvable keys (logs skip reason).

        Field mapping notes:
        - modalidad_de_contrataci_n has an accent in the API field name
        - fecha_inicio_ejecuci_n and fecha_fin_ejecuci_n also have accents
        - Contrato composite key: numero_del_contrato + "_" + origen
        """
        records = []
        ingested_at = datetime.now(timezone.utc).isoformat()
        skipped = 0

        for row in df.to_dicts():
            # Mandatory: entidad identifier
            codigo_entidad = (row.get("codigo_entidad_en_secop") or "").strip()
            if not codigo_entidad:
                logger.warning("Skipping row — missing codigo_entidad_en_secop")
                skipped += 1
                continue

            # Mandatory: contract composite key
            numero = (row.get("numero_del_contrato") or "").strip()
            origen = (row.get("origen") or "").strip()
            if not numero or not origen:
                logger.warning("Skipping row — missing numero_del_contrato or origen")
                skipped += 1
                continue

            id_contrato = f"{numero}_{origen}"

            # Handle SEMIPRIVADA fields
            documento_raw = row.get("documento_proveedor") or ""
            tipo_doc_raw = row.get("tipo_documento_proveedor") or ""
            proveedor_type = classify_proveedor_type(documento_raw, tipo_doc_raw)

            record = {
                # EntidadPublica fields
                "codigo_entidad": codigo_entidad,
                "nombre_entidad": row.get("nombre_de_la_entidad") or "",
                "nivel_entidad": row.get("nivel_entidad") or "",
                "nit_entidad": normalize_nit(row.get("nit_de_la_entidad")),
                "departamento_entidad": row.get("departamento_entidad") or "",
                "municipio_entidad": row.get("municipio_entidad") or "",
                # Contrato fields
                "id_contrato": id_contrato,
                "valor_contrato": _parse_valor(row.get("valor_contrato")),
                "objeto_contrato": row.get("objeto_a_contratar") or row.get("objeto_del_proceso") or "",
                "tipo_contrato": row.get("tipo_de_contrato") or "",
                "modalidad": row.get("modalidad_de_contrataci_n") or "",
                "estado_proceso": row.get("estado_del_proceso") or "",
                "fecha_firma": row.get("fecha_de_firma_del_contrato") or "",
                "fecha_inicio": row.get("fecha_inicio_ejecuci_n") or "",
                "fecha_fin": row.get("fecha_fin_ejecuci_n") or "",
                "numero_proceso": row.get("numero_de_proceso") or "",
                "origen": origen,
                # Provenance (ETL-07)
                "fuente": FUENTE,
                "ingested_at": ingested_at,
                "url_contrato": row.get("url_contrato") or "",
                # Contractor fields
                "razon_social": row.get("nom_raz_social_contratista") or "",
                "tipo_documento_proveedor": tipo_doc_raw,
                "proveedor_type": proveedor_type,
                "nit_contratista": normalize_nit(documento_raw) if proveedor_type == "empresa" else None,
                "cedula_contratista": normalize_nit(documento_raw) if proveedor_type == "persona" else None,
            }
            records.append(record)

        if skipped:
            logger.info("Skipped %d records with missing required keys", skipped)

        return records

    def get_cypher(self) -> str:
        # This method exists to satisfy BasePipeline but is not used here —
        # SecopIntegradoPipeline uses multiple Cypher statements (load() override below).
        return CYPHER_ENTIDAD_CONTRATO

    async def load(self, records: list[dict], loader: Neo4jLoader) -> int:
        """
        Override base load to execute three separate MERGE passes:
        1. EntidadPublica + Contrato + ADJUDICO relationship
        2. Empresa + EJECUTA relationship (for empresa proveedores)
        3. Persona + EJECUTA relationship (for persona proveedores)
        """
        total = 0

        # Pass 1: All records — entities and contracts
        total += await loader.merge_batch(records, CYPHER_ENTIDAD_CONTRATO)

        # Pass 2: Empresa contractors (NIT normalized, non-null)
        empresa_records = [r for r in records if r["proveedor_type"] == "empresa" and r["nit_contratista"]]
        if empresa_records:
            total += await loader.merge_batch(empresa_records, CYPHER_EMPRESA_EJECUTA)
            logger.info("Merged %d Empresa contractor records", len(empresa_records))

        # Pass 3: Persona contractors (cedula normalized, non-null)
        persona_records = [r for r in records if r["proveedor_type"] == "persona" and r["cedula_contratista"]]
        if persona_records:
            total += await loader.merge_batch(persona_records, CYPHER_PERSONA_EJECUTA)
            logger.info("Merged %d Persona contractor records", len(persona_records))

        desconocido_count = sum(1 for r in records if r["proveedor_type"] == "desconocido")
        if desconocido_count:
            logger.warning("Skipped %d records with unknown proveedor type (no contractor node created)", desconocido_count)

        return total


def _parse_valor(raw) -> float | None:
    """Parse contract value: remove thousands separators, return float or None."""
    if raw is None:
        return None
    try:
        # Remove dots used as thousands separators (Colombian convention)
        cleaned = str(raw).replace(".", "").replace(",", ".").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None
