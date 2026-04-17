"""
Unit tests for SiriSancionesPipeline.

Tests cover:
- transform() field mapping and skip conditions
- SIRI pitfall: trailing whitespace on numero_identificacion MUST be stripped BEFORE normalize_cedula()
- SIRI pitfall: fecha_efectos_juridicos stored as DD/MM/YYYY string (no ISO parse)
- nombre_completo assembly from name parts
- Persona.nombre NOT overwritten on MATCH (ON MATCH only sets updated_at)
- id_sancion uses numero_siri directly
- load() executes exactly 2 merge_batch() calls
"""

from unittest.mock import AsyncMock, MagicMock, patch, call

import polars as pl
import pytest

from etl.sources.siri_sanciones import SiriSancionesPipeline


@pytest.fixture
def pipeline():
    return SiriSancionesPipeline()


def _make_row(**kwargs):
    """Build a minimal valid SIRI row."""
    defaults = {
        "numero_siri": "SIRI-001",
        "numero_identificacion": "12345678",
        "primer_nombre": "JUAN",
        "segundo_nombre": "CARLOS",
        "primer_apellido": "PEREZ",
        "segundo_apellido": "GARCIA",
        "tipo_inhabilidad": "SUSPENSION",
        "sanciones": "SUSPENSION EN EL EJERCICIO DEL CARGO",
        "calidad_persona": "SERVIDOR PUBLICO",
        "cargo": "DIRECTOR",
        "duracion_anos": "1",
        "duracion_mes": "0",
        "duracion_dias": "0",
        "providencia": "FALLO-2020-001",
        "autoridad": "PROCURADURIA",
        "fecha_efectos_juridicos": "22/04/2005",
        "numero_proceso": "PROC-001",
        "entidad_sancionado": "MINISTERIO DE EDUCACION",
        "lugar_hechos_departamento": "CUNDINAMARCA",
        "lugar_hechos_municipio": "BOGOTA",
    }
    defaults.update(kwargs)
    return defaults


def _make_df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


class TestTransformBasicFieldMapping:
    """transform() correctly maps SIRI API fields."""

    def test_id_sancion_from_numero_siri(self, pipeline):
        df = _make_df([_make_row(numero_siri="SIRI-XYZ-999")])
        records = pipeline.transform(df)
        assert len(records) == 1
        assert records[0]["id_sancion"] == "SIRI-XYZ-999"

    def test_cedula_from_numero_identificacion(self, pipeline):
        df = _make_df([_make_row(numero_identificacion="79123456")])
        records = pipeline.transform(df)
        assert records[0]["cedula"] == "79123456"

    def test_fuente_is_dataset_id(self, pipeline):
        df = _make_df([_make_row()])
        records = pipeline.transform(df)
        assert records[0]["fuente"] == "iaeu-rcn6"

    def test_fecha_efectos_stored_as_string_not_iso(self, pipeline):
        """fecha_efectos_juridicos is DD/MM/YYYY — store as-is (do NOT parse to ISO)."""
        df = _make_df([_make_row(fecha_efectos_juridicos="22/04/2005")])
        records = pipeline.transform(df)
        assert records[0]["fecha_efectos"] == "22/04/2005"

    def test_tipo_sancion_from_sanciones_field(self, pipeline):
        df = _make_df([_make_row(sanciones="MULTA")])
        records = pipeline.transform(df)
        assert records[0]["tipo_sancion"] == "MULTA"

    def test_ingested_at_is_set(self, pipeline):
        df = _make_df([_make_row()])
        records = pipeline.transform(df)
        assert "ingested_at" in records[0]
        assert records[0]["ingested_at"]


class TestTrailingWhitespacePitfall:
    """CRITICAL: strip() MUST be called before normalize_cedula() on numero_identificacion."""

    def test_trailing_whitespace_stripped_before_normalize(self, pipeline):
        """numero_identificacion arrives padded: '7534386        '"""
        df = _make_df([_make_row(numero_identificacion="7534386        ")])
        records = pipeline.transform(df)
        assert len(records) == 1
        assert records[0]["cedula"] == "7534386"

    def test_leading_whitespace_stripped_too(self, pipeline):
        df = _make_df([_make_row(numero_identificacion="  79123456  ")])
        records = pipeline.transform(df)
        assert records[0]["cedula"] == "79123456"


class TestNombreCompletoAssembly:
    """nombre_completo assembled from 4 name parts, skipping None."""

    def test_all_four_parts(self, pipeline):
        df = _make_df([_make_row(
            primer_nombre="JUAN",
            segundo_nombre="CARLOS",
            primer_apellido="PEREZ",
            segundo_apellido="GARCIA",
        )])
        records = pipeline.transform(df)
        assert records[0]["nombre_completo"] == "JUAN CARLOS PEREZ GARCIA"

    def test_missing_segundo_nombre(self, pipeline):
        row = _make_row()
        del row["segundo_nombre"]
        df = _make_df([row])
        records = pipeline.transform(df)
        assert records[0]["nombre_completo"] == "JUAN PEREZ GARCIA"

    def test_none_segundo_nombre(self, pipeline):
        df = _make_df([_make_row(segundo_nombre=None)])
        records = pipeline.transform(df)
        assert records[0]["nombre_completo"] == "JUAN PEREZ GARCIA"

    def test_slash_in_name_part_skipped(self, pipeline):
        """Names with '/' are placeholder/corrupt values — skip."""
        df = _make_df([_make_row(segundo_nombre="/")])
        records = pipeline.transform(df)
        assert records[0]["nombre_completo"] == "JUAN PEREZ GARCIA"

    def test_all_parts_none(self, pipeline):
        df = _make_df([_make_row(
            primer_nombre=None,
            segundo_nombre=None,
            primer_apellido=None,
            segundo_apellido=None,
        )])
        records = pipeline.transform(df)
        assert records[0]["nombre_completo"] == ""


class TestSkipConditions:
    """transform() skips records with unresolvable mandatory keys."""

    def test_skip_when_numero_siri_empty(self, pipeline):
        df = _make_df([_make_row(numero_siri="")])
        records = pipeline.transform(df)
        assert records == []

    def test_skip_when_numero_siri_missing(self, pipeline):
        row = _make_row()
        del row["numero_siri"]
        df = _make_df([row])
        records = pipeline.transform(df)
        assert records == []

    def test_skip_when_cedula_normalizes_to_none(self, pipeline):
        """Non-numeric identification -> normalize_cedula returns None -> skip."""
        df = _make_df([_make_row(numero_identificacion="N/A")])
        records = pipeline.transform(df)
        assert records == []

    def test_skip_when_numero_identificacion_empty(self, pipeline):
        df = _make_df([_make_row(numero_identificacion="")])
        records = pipeline.transform(df)
        assert records == []

    def test_valid_record_passes(self, pipeline):
        df = _make_df([_make_row()])
        records = pipeline.transform(df)
        assert len(records) == 1


class TestLoadTwoPasses:
    """load() must execute exactly 2 merge_batch() calls."""

    @pytest.mark.asyncio
    async def test_load_calls_merge_batch_twice(self, pipeline):
        loader = MagicMock()
        loader.merge_batch = AsyncMock(return_value=1)

        records = [
            {"id_sancion": "S1", "cedula": "123", "nombre_completo": "JUAN PEREZ",
             "tipo_inhabilidad": None, "tipo_sancion": None, "calidad_persona": None,
             "cargo_sancionado": None, "duracion_anos": None, "duracion_mes": None,
             "duracion_dias": None, "providencia": None, "autoridad": None,
             "fecha_efectos": None, "numero_proceso": None, "entidad_sancionado": None,
             "lugar_hechos_departamento": None, "lugar_hechos_municipio": None,
             "fuente": "iaeu-rcn6", "ingested_at": "2026-01-01T00:00:00Z"},
        ]

        await pipeline.load(records, loader)
        assert loader.merge_batch.call_count == 2


class TestCypherStructure:
    """Verify Cypher constants have required patterns."""

    def test_sancion_cypher_has_merge_on_id_sancion(self, pipeline):
        from etl.sources.siri_sanciones import CYPHER_SANCION
        assert "MERGE (s:Sancion {id_sancion: row.id_sancion})" in CYPHER_SANCION

    def test_persona_cypher_has_sancionado_relationship(self, pipeline):
        from etl.sources.siri_sanciones import CYPHER_PERSONA_SANCIONADO
        assert "SANCIONADO" in CYPHER_PERSONA_SANCIONADO

    def test_persona_cypher_on_match_does_not_set_nombre(self):
        """Persona.nombre is NOT overwritten on MATCH — preserve SECOP-sourced names."""
        from etl.sources.siri_sanciones import CYPHER_PERSONA_SANCIONADO
        # Split on ON MATCH SET and check that "nombre" does not appear after it
        parts = CYPHER_PERSONA_SANCIONADO.split("ON MATCH SET")
        assert len(parts) >= 2
        on_match_section = parts[1]
        assert "nombre" not in on_match_section

    def test_persona_cypher_merge_on_cedula(self):
        from etl.sources.siri_sanciones import CYPHER_PERSONA_SANCIONADO
        assert "MERGE (p:Persona {cedula: row.cedula})" in CYPHER_PERSONA_SANCIONADO
