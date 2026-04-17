"""
SECOP II Procesos de Compra (p6dx-8zbt) ETL pipeline.

Loads SECOP II procurement process data from datos.gov.co Socrata API into Neo4j.
Creates: :Proceso nodes with offer counts, publication dates, and pricing.
Links:   (EntidadPublica)-[:PUBLICO]->(Proceso)
         (Empresa)-[:PARTICIPO]->(Proceso) for adjudicated providers.

Key fields for pattern detection:
- proveedores_unicos_con  -> numero_oferentes  (PAT single-bidder)
- fecha_de_publicacion_del / fecha_de_recepcion_de (PAT short-tender)
- precio_base / valor_total_adjudicacion (PAT value anomalies)

Dataset size: ~8.4M records. Incremental by fecha_de_publicacion_del.
"""

import asyncio
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

DATASET_ID = "p6dx-8zbt"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
FUENTE = DATASET_ID

# ---------------------------------------------------------------------------
# Cypher — two-pass pattern
# ---------------------------------------------------------------------------

CYPHER_ENTIDAD_PROCESO = """
UNWIND $batch AS row

MERGE (ent:EntidadPublica {codigo_entidad: row.codigo_entidad})
ON CREATE SET
    ent.nombre        = row.nombre_entidad,
    ent.nit           = row.nit_entidad,
    ent.departamento  = row.departamento,
    ent.municipio     = row.municipio,
    ent.orden         = row.orden,
    ent.fuente        = row.fuente,
    ent.ingested_at   = datetime()
ON MATCH SET
    ent.nombre        = row.nombre_entidad,
    ent.updated_at    = datetime()

MERGE (p:Proceso {referencia_proceso: row.id_proceso})
ON CREATE SET
    p.referencia_entidad = row.referencia_proceso,
    p.objeto             = row.objeto,
    p.modalidad          = row.modalidad,
    p.estado             = row.estado,
    p.fase               = row.fase,
    p.tipo               = row.tipo_contrato,
    p.fecha_publicacion  = row.fecha_publicacion,
    p.fecha_cierre       = row.fecha_cierre,
    p.fecha_adjudicacion = row.fecha_adjudicacion,
    p.numero_oferentes   = row.numero_oferentes,
    p.proveedores_invitados = row.proveedores_invitados,
    p.precio_base        = row.precio_base,
    p.valor_adjudicacion = row.valor_adjudicacion,
    p.duracion           = row.duracion,
    p.unidad_duracion    = row.unidad_duracion,
    p.adjudicado         = row.adjudicado,
    p.url_fuente         = row.url_proceso,
    p.fuente             = row.fuente,
    p.ingested_at        = datetime()
ON MATCH SET
    p.estado             = row.estado,
    p.fase               = row.fase,
    p.numero_oferentes   = row.numero_oferentes,
    p.valor_adjudicacion = row.valor_adjudicacion,
    p.adjudicado         = row.adjudicado,
    p.updated_at         = datetime()

MERGE (ent)-[:PUBLICO]->(p)
"""

CYPHER_EMPRESA_PARTICIPO = """
UNWIND $batch AS row
MERGE (e:Empresa {nit: row.nit_proveedor})
ON CREATE SET
    e.razon_social  = row.nombre_proveedor,
    e.fuente        = row.fuente,
    e.ingested_at   = datetime()
ON MATCH SET
    e.razon_social  = COALESCE(
        CASE WHEN row.nombre_proveedor <> 'No Definido' THEN row.nombre_proveedor ELSE null END,
        e.razon_social
    ),
    e.updated_at    = datetime()
WITH e, row
MATCH (p:Proceso {referencia_proceso: row.id_proceso})
MERGE (e)-[:PARTICIPO]->(p)
"""


class SecopIIProcesosPipeline(BasePipeline):
    name = DATASET_ID
    label = "SECOP II Procesos de Compra"

    async def extract(self, state: RunState) -> AsyncGenerator[pl.DataFrame, None]:
        """Paginate SECOP II Procesos via Socrata SODA API."""
        params: dict = {
            "$limit": etl_config.page_size,
            "$order": "fecha_de_publicacion_del ASC",
        }

        last_run_at = state.get("last_run_at")
        if last_run_at:
            params["$where"] = f"fecha_de_publicacion_del > '{last_run_at}'"

        headers = {}
        if etl_config.socrata_app_token:
            headers["X-App-Token"] = etl_config.socrata_app_token

        offset = state.get("last_page", 0) * etl_config.page_size
        page = state.get("last_page", 0)

        async with httpx.AsyncClient(timeout=etl_config.http_timeout) as client:
            while True:
                params["$offset"] = offset

                # Retry up to 5 times on transient Socrata errors (500, 502, 503, timeout)
                for attempt in range(5):
                    try:
                        response = await client.get(BASE_URL, params=params, headers=headers)
                        response.raise_for_status()
                        break
                    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                        if attempt < 4:
                            wait = 10 * (attempt + 1)
                            logger.warning("Socrata error at offset %d (attempt %d/5): %s — retrying in %ds", offset, attempt + 1, exc, wait)
                            await asyncio.sleep(wait)
                        else:
                            raise

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
        """Normalize SECOP II Procesos rows for Neo4j MERGE."""
        records = []
        skipped = 0

        for row in df.to_dicts():
            # Mandatory: process ID
            id_proceso = (row.get("id_del_proceso") or "").strip()
            if not id_proceso:
                skipped += 1
                continue

            # Mandatory: entidad identifier
            codigo_entidad = str(row.get("codigo_entidad") or "").strip()
            if not codigo_entidad:
                skipped += 1
                continue

            # Parse numeric fields
            numero_oferentes = _parse_int(row.get("proveedores_unicos_con"))
            proveedores_invitados = _parse_int(row.get("proveedores_invitados"))
            precio_base = _parse_float(row.get("precio_base"))
            valor_adjudicacion = _parse_float(row.get("valor_total_adjudicacion"))
            duracion = _parse_int(row.get("duracion"))

            # Provider NIT — only if adjudicated and not sentinel
            nit_raw = (row.get("nit_del_proveedor_adjudicado") or "").strip()
            nit_proveedor = None
            nombre_proveedor = (row.get("nombre_del_proveedor") or "").strip()
            if nit_raw and nit_raw != "No Definido" and nombre_proveedor != "No Definido":
                nit_proveedor = normalize_nit(nit_raw)

            # URL may come as dict {"url": "..."} or plain string
            url_raw = row.get("urlproceso") or ""
            if isinstance(url_raw, dict):
                url_proceso = url_raw.get("url", "")
            else:
                url_proceso = str(url_raw)

            record = {
                # EntidadPublica
                "codigo_entidad": codigo_entidad,
                "nombre_entidad": (row.get("entidad") or "").strip(),
                "nit_entidad": normalize_nit(row.get("nit_entidad")),
                "departamento": row.get("departamento_entidad") or "",
                "municipio": row.get("ciudad_entidad") or "",
                "orden": row.get("ordenentidad") or "",
                # Proceso
                "id_proceso": id_proceso,
                "referencia_proceso": (row.get("referencia_del_proceso") or "").strip(),
                "objeto": (row.get("nombre_del_procedimiento") or "").strip(),
                "modalidad": (row.get("modalidad_de_contratacion") or "").strip(),
                "estado": (row.get("estado_del_procedimiento") or "").strip(),
                "fase": (row.get("fase") or "").strip(),
                "tipo_contrato": (row.get("tipo_de_contrato") or "").strip(),
                "fecha_publicacion": row.get("fecha_de_publicacion_del") or "",
                "fecha_cierre": row.get("fecha_de_recepcion_de") or "",
                "fecha_adjudicacion": row.get("fecha_adjudicacion") or "",
                "numero_oferentes": numero_oferentes,
                "proveedores_invitados": proveedores_invitados,
                "precio_base": precio_base,
                "valor_adjudicacion": valor_adjudicacion,
                "duracion": duracion,
                "unidad_duracion": row.get("unidad_de_duracion") or "",
                "adjudicado": (row.get("adjudicado") or "").strip(),
                "url_proceso": url_proceso,
                # Provider (for pass 2)
                "nit_proveedor": nit_proveedor,
                "nombre_proveedor": nombre_proveedor,
                # Provenance
                "fuente": FUENTE,
            }
            records.append(record)

        if skipped:
            logger.info("Skipped %d records with missing required keys", skipped)

        return records

    def get_cypher(self) -> str:
        return CYPHER_ENTIDAD_PROCESO

    async def load(self, records: list[dict], loader: Neo4jLoader) -> int:
        """Two-pass MERGE: EntidadPublica+Proceso, then Empresa adjudicataria."""
        total = 0

        # Pass 1: All records — entities and processes
        total += await loader.merge_batch(records, CYPHER_ENTIDAD_PROCESO)

        # Pass 2: Adjudicated empresa providers (with valid NIT)
        empresa_records = [r for r in records if r["nit_proveedor"] is not None]
        if empresa_records:
            total += await loader.merge_batch(empresa_records, CYPHER_EMPRESA_PARTICIPO)
            logger.info("Merged %d adjudicated Empresa records", len(empresa_records))

        return total


def _parse_int(raw) -> int | None:
    if raw is None:
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        return None


def _parse_float(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except (ValueError, TypeError):
        return None
