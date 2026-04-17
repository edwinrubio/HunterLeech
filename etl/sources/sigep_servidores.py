"""
SIGEP Servidores Publicos (2jzx-383z) ETL pipeline.

Loads public servant directory data from datos.gov.co Socrata API into Neo4j.
Creates: :EntidadPublica, :Persona nodes
Creates: (Persona)-[:EMPLEA_EN]->(EntidadPublica)

Key design decisions:
- EntidadPublica MERGE key = nombre (NOT codigo_entidad — SIGEP has no codigo_entidad field;
  MERGE on null would violate the unique constraint on codigo_entidad)
- Persona MERGE key = cedula (from numerodeidentificacion field after normalize_cedula())
- SIGEP nombre field = numerodeidentificacion (privacy redaction by SIGEP); NEVER write
  to Persona.nombre — the field contains the ID number, not the person's name.
- Salary field asignacionbasicasalarial uses commas as thousands separator: "1,440,300"
- Sort field has accent substitution: fecha_de_vinculaci_n (underscore not ñ in field name)

Provenance (ETL-07): every node carries fuente='2jzx-383z', ingested_at=datetime()
Idempotence (ETL-08): all writes use MERGE ON CREATE / ON MATCH — re-run safe
Entity linking (ETL-06): MERGE on cedula automatically links Persona nodes that
  already exist from SECOP sources — no explicit join needed.
"""

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
import polars as pl

from etl.base import BasePipeline
from etl.config import etl_config
from etl.normalizers.common import normalize_cedula
from etl.state import RunState

logger = logging.getLogger(__name__)

DATASET_ID = "2jzx-383z"
BASE_URL = f"https://www.datos.gov.co/resource/{DATASET_ID}.json"
FUENTE = DATASET_ID  # provenance tag on every node


# ---------------------------------------------------------------------------
# Cypher — single-pass (Persona + EntidadPublica + EMPLEA_EN relationship)
# Uses nombre MERGE for EntidadPublica (NOT codigo_entidad — SIGEP pitfall)
# ---------------------------------------------------------------------------

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
    p.sexo                    = row.sexo,
    p.departamento_nacimiento = row.departamento_nacimiento,
    p.municipio_nacimiento    = row.municipio_nacimiento,
    p.nivel_educativo         = row.nivel_educativo,
    p.fuente                  = row.fuente,
    p.ingested_at             = datetime()
ON MATCH SET
    p.updated_at              = datetime()

MERGE (p)-[r:EMPLEA_EN {codigo_sigep: row.codigo_sigep}]->(ent)
ON CREATE SET
    r.cargo             = row.cargo,
    r.dependencia       = row.dependencia,
    r.nivel_jerarquico  = row.nivel_jerarquico,
    r.tipo_nombramiento = row.tipo_nombramiento,
    r.salario_basico    = row.salario_basico,
    r.fecha_vinculacion = row.fecha_vinculacion,
    r.fuente            = row.fuente
ON MATCH SET
    r.salario_basico    = COALESCE(row.salario_basico, r.salario_basico),
    r.updated_at        = datetime()
"""


def _parse_salario(raw) -> float | None:
    """SIGEP uses commas as thousands separator: '1,440,300' -> 1440300.0"""
    if raw is None:
        return None
    try:
        cleaned = str(raw).replace(",", "").strip()
        if not cleaned:
            return None
        return float(cleaned)
    except (ValueError, TypeError):
        return None


class SigepServidoresPipeline(BasePipeline):
    name = DATASET_ID
    label = "SIGEP Servidores Publicos"

    async def extract(self, state: RunState) -> AsyncGenerator[pl.DataFrame, None]:
        """
        Paginate SIGEP Servidores dataset via Socrata SODA API.
        Sort field: fecha_de_vinculaci_n (underscore — accent substitution in field name).
        For incremental runs, filters by fecha_de_vinculaci_n > last_run_at.
        """
        params: dict = {
            "$limit": etl_config.page_size,
            "$order": "fecha_de_vinculaci_n ASC",
        }

        last_run_at = state.get("last_run_at")
        if last_run_at:
            params["$where"] = f"fecha_de_vinculaci_n > '{last_run_at}'"

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
        Normalize SIGEP rows into dicts ready for Neo4j MERGE.
        Skips records with unresolvable keys (logs skip reason).

        Field mapping notes:
        - numerodeidentificacion -> cedula (MERGE key for Persona)
        - nombre field is INTENTIONALLY IGNORED — it contains numerodeidentificacion
          (SIGEP privacy redaction). Never read nombre for Persona.nombre.
        - nombreentidad -> nombre_entidad (MERGE key for EntidadPublica — no codigo_entidad)
        - asignacionbasicasalarial uses comma thousands separator -> _parse_salario()
        """
        records = []
        ingested_at = datetime.now(timezone.utc).isoformat()
        skipped = 0

        for row in df.to_dicts():
            # Mandatory: Persona cedula (from numerodeidentificacion — NEVER from nombre)
            cedula_raw = (row.get("numerodeidentificacion") or "").strip()
            cedula = normalize_cedula(cedula_raw)
            if not cedula:
                logger.warning(
                    "Skipping SIGEP row — normalize_cedula(%r) returned None", cedula_raw
                )
                skipped += 1
                continue

            # Mandatory: EntidadPublica MERGE key is nombre (no codigo_entidad in SIGEP)
            nombre_entidad = (row.get("nombreentidad") or "").strip()
            if not nombre_entidad:
                logger.warning("Skipping SIGEP row — missing nombreentidad (required for MERGE)")
                skipped += 1
                continue

            record = {
                # Persona fields (cedula is the MERGE key)
                "cedula": cedula,
                # NOTE: 'nombre' field intentionally omitted — SIGEP nombre = numerodeidentificacion
                "sexo": row.get("sexo"),
                "departamento_nacimiento": row.get("departamentodenacimiento"),
                "municipio_nacimiento": row.get("municipiodenacimiento"),
                "nivel_educativo": row.get("niveleducativo"),
                # EntidadPublica fields (nombre is the MERGE key for SIGEP entities)
                "nombre_entidad": nombre_entidad,
                "orden": row.get("orden"),
                "naturaleza": row.get("naturalezajuridica"),
                # Employment relationship fields
                "cargo": row.get("denominacionempleoactual"),
                "dependencia": row.get("dependenciaempleoactual"),
                "nivel_jerarquico": row.get("niveljerarquicoempleo"),
                "tipo_nombramiento": row.get("tipodenombramiento"),
                "codigo_sigep": row.get("codigosigep"),
                "salario_basico": _parse_salario(row.get("asignacionbasicasalarial")),
                "fecha_vinculacion": row.get("fecha_de_vinculaci_n"),
                # Provenance (ETL-07)
                "fuente": FUENTE,
                "ingested_at": ingested_at,
            }
            records.append(record)

        if skipped:
            logger.info("Skipped %d SIGEP records with missing required keys", skipped)

        return records

    def get_cypher(self) -> str:
        return CYPHER_SIGEP
