"""
SECOP II Contratos Electronicos (jbjy-vk9h) ETL pipeline.

Loads SECOP II electronic contract data from datos.gov.co Socrata API into Neo4j.
Creates: :EntidadPublica, :Empresa/:Persona (contractor), :Contrato nodes
Creates: (EntidadPublica)-[:ADJUDICO]->(Contrato), (Empresa|Persona)-[:EJECUTA]->(Contrato)

Key design decisions:
- id_contrato is used directly as the Contrato MERGE key (globally unique in SECOP II:
  format "CO1.PCCNTR.<number>"). Unlike SECOP I, no composite key is needed.
- valor_del_contrato is a plain integer string in SECOP II — NO dot removal.
  SECOP I uses dots as thousands separators; SECOP II does not. Use _parse_valor_secop2().
- tipodocproveedor values: "NIT" (empresa) or "Cédula de Ciudadanía" (persona).
  Classification delegates to classify_proveedor_type() from etl.normalizers.common.
- Documents where proveedor_type resolves to "desconocido" skip contractor MERGE.
- Same three-pass MERGE pattern as SecopIntegradoPipeline (Anti-Pattern 1 compliance).
- Provenance: fuente='jbjy-vk9h', ingested_at=datetime(), url_fuente on every Contrato node.
- Idempotence: all writes use MERGE ON CREATE / ON MATCH — re-run safe.
- Cross-source linking: Empresa.nit and Persona.cedula share namespace with SECOP I;
  MERGE on normalized key automatically links entities appearing in both datasets.

Privacy (Ley 1581/2012):
- documento_proveedor is SEMIPRIVADA when tipodocproveedor is cedula-based.
- Representative/supervisor name fields are SEMIPRIVADA — not loaded.
- Bank account fields are PRIVADA — never loaded.

Pitfalls (per RESEARCH.md):
- Pitfall 4: SECOP II uses plain integer strings for valor — do NOT strip dots.
- Sort field is fecha_de_firma (not fecha_de_firma_del_contrato as in SECOP I).
- modalidad_de_contratacion has NO accent in SECOP II (contrast with SECOP I).
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
)
from etl.state import RunState

logger = logging.getLogger(__name__)

DATASET_ID = "jbjy-vk9h"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
FUENTE = DATASET_ID  # provenance tag on every node


# ---------------------------------------------------------------------------
# Cypher — three-pass pattern (ARCHITECTURE Anti-Pattern 1 compliance)
# ---------------------------------------------------------------------------

CYPHER_ENTIDAD_CONTRATO = """
UNWIND $batch AS row

// 1. MERGE EntidadPublica node
MERGE (ent:EntidadPublica {codigo_entidad: row.codigo_entidad})
ON CREATE SET
    ent.nombre        = row.nombre_entidad,
    ent.nit           = row.nit_entidad,
    ent.departamento  = row.departamento,
    ent.municipio     = row.municipio,
    ent.sector        = row.sector,
    ent.orden         = row.orden,
    ent.fuente        = row.fuente,
    ent.ingested_at   = datetime()
ON MATCH SET
    ent.nombre        = row.nombre_entidad,
    ent.updated_at    = datetime()

// 2. MERGE Contrato node (direct id_contrato key — globally unique in SECOP II)
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

// 3. MERGE ADJUDICO relationship (entity -> contract)
MERGE (ent)-[:ADJUDICO {modalidad: row.modalidad}]->(c)
"""

CYPHER_EMPRESA_EJECUTA = """
UNWIND $batch AS row
MERGE (e:Empresa {nit: row.nit_contratista})
ON CREATE SET
    e.razon_social      = row.razon_social,
    e.codigo_proveedor  = row.codigo_proveedor,
    e.fuente            = row.fuente,
    e.ingested_at       = datetime()
ON MATCH SET
    e.razon_social      = row.razon_social,
    e.updated_at        = datetime()
WITH e, row
MATCH (c:Contrato {id_contrato: row.id_contrato})
MERGE (e)-[:EJECUTA]->(c)
"""

CYPHER_PERSONA_EJECUTA = """
UNWIND $batch AS row
MERGE (p:Persona {cedula: row.cedula_contratista})
ON CREATE SET
    p.nombre            = row.razon_social,
    p.codigo_proveedor  = row.codigo_proveedor,
    p.fuente            = row.fuente,
    p.ingested_at       = datetime()
ON MATCH SET
    p.nombre            = row.razon_social,
    p.updated_at        = datetime()
WITH p, row
MATCH (c:Contrato {id_contrato: row.id_contrato})
MERGE (p)-[:EJECUTA]->(c)
"""


class SecopIIContratosPipeline(BasePipeline):
    name = DATASET_ID
    label = "SECOP II Contratos Electronicos"

    async def extract(self, state: RunState) -> AsyncGenerator[pl.DataFrame, None]:
        """
        Paginate SECOP II Contratos dataset via Socrata SODA API.
        Sort field: fecha_de_firma (not fecha_de_firma_del_contrato — SECOP I name).
        For incremental runs, filters by fecha_de_firma > last_run_at.
        """
        params: dict = {
            "$limit": etl_config.page_size,
            "$order": "fecha_de_firma ASC",
        }

        last_run_at = state.get("last_run_at")
        if last_run_at:
            params["$where"] = f"fecha_de_firma > '{last_run_at}'"

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
        Normalize SECOP II Contratos rows into dicts ready for Neo4j MERGE.
        Skips records with missing mandatory keys (logs skip reason).

        Field mapping notes (per RESEARCH.md):
        - id_contrato: used directly, no composite (globally unique in SECOP II)
        - valor_del_contrato: plain integer string — NO dot removal (SECOP II Pitfall 4)
        - modalidad_de_contratacion: NO accent in SECOP II field name (vs SECOP I)
        - tipodocproveedor values: "NIT" or "Cédula de Ciudadanía"
        """
        records = []
        ingested_at = datetime.now(timezone.utc).isoformat()
        skipped = 0

        for row in df.to_dicts():
            # Mandatory: entidad identifier
            codigo_entidad = (row.get("codigo_entidad") or "").strip()
            if not codigo_entidad:
                logger.warning("Skipping row — missing codigo_entidad")
                skipped += 1
                continue

            # Mandatory: contract key (direct, globally unique — no composite)
            id_contrato = (row.get("id_contrato") or "").strip()
            if not id_contrato:
                logger.warning("Skipping row — missing id_contrato")
                skipped += 1
                continue

            # Classify proveedor type (delegates to normalizers — no inline logic)
            documento_proveedor = row.get("documento_proveedor") or ""
            tipodocproveedor = row.get("tipodocproveedor") or ""
            proveedor_type = classify_proveedor_type(documento_proveedor, tipodocproveedor)

            record = {
                # EntidadPublica fields
                "codigo_entidad": codigo_entidad,
                "nombre_entidad": row.get("nombre_entidad") or "",
                "nit_entidad": normalize_nit(row.get("nit_entidad")),
                "departamento": row.get("departamento") or "",
                "municipio": row.get("ciudad") or "",
                "sector": row.get("sector") or "",
                "orden": row.get("orden") or "",
                # Contrato fields
                "id_contrato": id_contrato,
                "valor_contrato": _parse_valor_secop2(row.get("valor_del_contrato")),
                "objeto_contrato": row.get("objeto_del_contrato") or "",
                "tipo_contrato": row.get("tipo_de_contrato") or "",
                "modalidad": row.get("modalidad_de_contratacion") or "",
                "estado_contrato": row.get("estado_contrato") or "",
                "fecha_firma": row.get("fecha_de_firma") or "",
                "fecha_inicio": row.get("fecha_de_inicio_del_contrato") or "",
                "fecha_fin": row.get("fecha_de_fin_del_contrato") or "",
                "proceso_compra": row.get("proceso_de_compra") or "",
                "url_proceso": row.get("urlproceso") or "",
                # Provenance (ETL-07)
                "fuente": FUENTE,
                "ingested_at": ingested_at,
                # Contractor fields
                "razon_social": row.get("proveedor_adjudicado") or "",
                "codigo_proveedor": row.get("codigo_proveedor") or "",
                "documento_proveedor": documento_proveedor,
                "tipodocproveedor": tipodocproveedor,
                "proveedor_type": proveedor_type,
                "nit_contratista": normalize_nit(documento_proveedor) if proveedor_type == "empresa" else None,
                "cedula_contratista": normalize_nit(documento_proveedor) if proveedor_type == "persona" else None,
            }
            records.append(record)

        if skipped:
            logger.info("Skipped %d records with missing required keys", skipped)

        return records

    def get_cypher(self) -> str:
        # Satisfies BasePipeline abstract method; not used directly since load() is overridden.
        return CYPHER_ENTIDAD_CONTRATO

    async def load(self, records: list[dict], loader: Neo4jLoader) -> int:
        """
        Override base load to execute three separate MERGE passes:
        1. EntidadPublica + Contrato + ADJUDICO relationship (all records)
        2. Empresa + EJECUTA relationship (empresa proveedores with valid NIT)
        3. Persona + EJECUTA relationship (persona proveedores with valid cedula)
        """
        total = 0

        # Pass 1: All records — entities and contracts
        total += await loader.merge_batch(records, CYPHER_ENTIDAD_CONTRATO)

        # Pass 2: Empresa contractors (NIT normalized, non-null)
        empresa_records = [
            r for r in records
            if r["proveedor_type"] == "empresa" and r["nit_contratista"] is not None
        ]
        total += await loader.merge_batch(empresa_records, CYPHER_EMPRESA_EJECUTA)
        if empresa_records:
            logger.info("Merged %d Empresa contractor records", len(empresa_records))

        # Pass 3: Persona contractors (cedula normalized, non-null)
        persona_records = [
            r for r in records
            if r["proveedor_type"] == "persona" and r["cedula_contratista"] is not None
        ]
        total += await loader.merge_batch(persona_records, CYPHER_PERSONA_EJECUTA)
        if persona_records:
            logger.info("Merged %d Persona contractor records", len(persona_records))

        desconocido_count = sum(1 for r in records if r["proveedor_type"] == "desconocido")
        if desconocido_count:
            logger.warning(
                "Skipped %d records with unknown proveedor type (no contractor node created)",
                desconocido_count,
            )

        return total


def _parse_valor_secop2(raw) -> float | None:
    """SECOP II values are plain integer strings — no dot removal.

    IMPORTANT: Do NOT reuse _parse_valor() from secop_integrado.py.
    SECOP I strips dots as thousands separators (Colombian convention).
    SECOP II uses plain integer strings — dots, if present, are decimal points.
    """
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except (ValueError, TypeError):
        return None
