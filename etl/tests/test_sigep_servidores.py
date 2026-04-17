"""
Unit tests for SigepServidoresPipeline.

Tests cover:
- transform() field mapping and skip conditions
- _parse_salario() helper
- get_cypher() structural requirements
- Entity linking: MERGE on cedula (not nombre)
- SIGEP pitfall: nombre field NEVER used for Persona.nombre
- SIGEP pitfall: EntidadPublica MERGES on nombre (not codigo_entidad)
"""

import polars as pl
import pytest

from etl.sources.sigep_servidores import SigepServidoresPipeline, _parse_salario


@pytest.fixture
def pipeline():
    return SigepServidoresPipeline()


def _make_row(**kwargs):
    """Build a minimal valid SIGEP row."""
    defaults = {
        "numerodeidentificacion": "12345678",
        "nombreentidad": "MINISTERIO DE EDUCACION",
        "sexo": "M",
        "departamentodenacimiento": "CUNDINAMARCA",
        "municipiodenacimiento": "BOGOTA",
        "niveleducativo": "UNIVERSITARIO",
        "denominacionempleoactual": "ANALISTA",
        "dependenciaempleoactual": "DIRECCION TI",
        "niveljerarquicoempleo": "PROFESIONAL",
        "tipodenombramiento": "CARRERA ADMINISTRATIVA",
        "codigosigep": "C001",
        "asignacionbasicasalarial": "3,500,000",
        "fecha_de_vinculaci_n": "2020-01-15T00:00:00.000",
        "orden": "NACIONAL",
        "naturalezajuridica": "ENTIDAD DESCENTRALIZADA",
    }
    defaults.update(kwargs)
    return defaults


def _make_df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


class TestTransformBasicFieldMapping:
    """transform() maps API fields to correct record keys."""

    def test_cedula_from_numerodeidentificacion(self, pipeline):
        df = _make_df([_make_row(numerodeidentificacion="12345678")])
        records = pipeline.transform(df)
        assert len(records) == 1
        assert records[0]["cedula"] == "12345678"

    def test_nombre_entidad_from_nombreentidad(self, pipeline):
        df = _make_df([_make_row(nombreentidad="ALCALDIA MAYOR DE BOGOTA")])
        records = pipeline.transform(df)
        assert records[0]["nombre_entidad"] == "ALCALDIA MAYOR DE BOGOTA"

    def test_fuente_is_dataset_id(self, pipeline):
        df = _make_df([_make_row()])
        records = pipeline.transform(df)
        assert records[0]["fuente"] == "2jzx-383z"

    def test_ingested_at_is_set(self, pipeline):
        df = _make_df([_make_row()])
        records = pipeline.transform(df)
        assert "ingested_at" in records[0]
        assert records[0]["ingested_at"]  # non-empty

    def test_salario_parsed_from_comma_separated(self, pipeline):
        df = _make_df([_make_row(asignacionbasicasalarial="1,440,300")])
        records = pipeline.transform(df)
        assert records[0]["salario_basico"] == 1440300.0

    def test_cargo_from_denominacionempleoactual(self, pipeline):
        df = _make_df([_make_row(denominacionempleoactual="DIRECTOR GENERAL")])
        records = pipeline.transform(df)
        assert records[0]["cargo"] == "DIRECTOR GENERAL"

    def test_sexo_mapped(self, pipeline):
        df = _make_df([_make_row(sexo="F")])
        records = pipeline.transform(df)
        assert records[0]["sexo"] == "F"

    def test_fecha_vinculacion_mapped(self, pipeline):
        df = _make_df([_make_row(**{"fecha_de_vinculaci_n": "2019-03-01T00:00:00.000"})])
        records = pipeline.transform(df)
        assert records[0]["fecha_vinculacion"] == "2019-03-01T00:00:00.000"


class TestTransformSkipConditions:
    """transform() skips records with missing mandatory keys."""

    def test_skip_when_cedula_none_after_normalize(self, pipeline):
        """normalize_cedula(non-numeric) returns None — record must be skipped."""
        df = _make_df([_make_row(numerodeidentificacion="N/A")])
        records = pipeline.transform(df)
        assert records == []

    def test_skip_when_numerodeidentificacion_empty(self, pipeline):
        df = _make_df([_make_row(numerodeidentificacion="")])
        records = pipeline.transform(df)
        assert records == []

    def test_skip_when_numerodeidentificacion_missing(self, pipeline):
        row = _make_row()
        del row["numerodeidentificacion"]
        df = _make_df([row])
        records = pipeline.transform(df)
        assert records == []

    def test_skip_when_nombre_entidad_empty(self, pipeline):
        """EntidadPublica MERGE key is nombre — skip if missing."""
        df = _make_df([_make_row(nombreentidad="")])
        records = pipeline.transform(df)
        assert records == []

    def test_skip_when_nombreentidad_missing(self, pipeline):
        row = _make_row()
        del row["nombreentidad"]
        df = _make_df([row])
        records = pipeline.transform(df)
        assert records == []

    def test_valid_records_with_numeric_cedula_pass(self, pipeline):
        df = _make_df([_make_row(numerodeidentificacion="79999999")])
        records = pipeline.transform(df)
        assert len(records) == 1


class TestTransformNombrePitfall:
    """CRITICAL: The SIGEP 'nombre' field contains numerodeidentificacion (ID number).
    It must NEVER be written to Persona.nombre."""

    def test_nombre_field_not_in_record(self, pipeline):
        """Record dict must NOT have a 'nombre' key."""
        row = _make_row()
        row["nombre"] = "THIS_IS_ACTUALLY_AN_ID"  # API field present
        df = _make_df([row])
        records = pipeline.transform(df)
        assert len(records) == 1
        # 'nombre' key must not appear in the record (or if it does, must be None/not used)
        assert "nombre" not in records[0]


class TestParseSalario:
    """_parse_salario() handles SIGEP's comma-separated thousands format."""

    def test_simple_commas(self):
        assert _parse_salario("1,440,300") == 1440300.0

    def test_no_commas(self):
        assert _parse_salario("3500000") == 3500000.0

    def test_none_input(self):
        assert _parse_salario(None) is None

    def test_empty_string(self):
        assert _parse_salario("") is None

    def test_invalid_string(self):
        assert _parse_salario("N/A") is None

    def test_numeric_string_with_spaces(self):
        assert _parse_salario("  2,000,000  ") == 2000000.0


class TestGetCypher:
    """get_cypher() must contain required MERGE patterns."""

    def test_merge_on_nombre_not_codigo_entidad(self, pipeline):
        cypher = pipeline.get_cypher()
        assert "MERGE (ent:EntidadPublica {nombre:" in cypher
        assert "codigo_entidad" not in cypher

    def test_merge_persona_on_cedula(self, pipeline):
        cypher = pipeline.get_cypher()
        assert "MERGE (p:Persona {cedula: row.cedula})" in cypher

    def test_emplea_en_relationship(self, pipeline):
        cypher = pipeline.get_cypher()
        assert "EMPLEA_EN" in cypher

    def test_unwind_batch(self, pipeline):
        cypher = pipeline.get_cypher()
        assert "UNWIND $batch AS row" in cypher
