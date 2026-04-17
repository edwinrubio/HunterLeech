"""
Unit tests for SecopMultasPipeline.

Tests cover:
- classify_contratista_type() name-based heuristics (no doc type discriminator)
- transform() field mapping and composite id_sancion construction
- transform() skip conditions
- transform() nit_entidad normalize_nit() call (handles check digit)
- transform() normalize_nit() on documento_contratista for both paths
- load() executes exactly 3 merge_batch() calls
"""

from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest

from etl.sources.secop_multas import SecopMultasPipeline, classify_contratista_type


@pytest.fixture
def pipeline():
    return SecopMultasPipeline()


def _make_row(**kwargs):
    """Build a minimal valid Multas row."""
    defaults = {
        "nit_entidad": "890000858-1",
        "nombre_entidad": "MINISTERIO DE HACIENDA",
        "nivel": "NACIONAL",
        "orden": "ADMINISTRATIVO",
        "municipio": "BOGOTA",
        "numero_de_resolucion": "RES-2020-001",
        "documento_contratista": "12345678",
        "nombre_contratista": "JUAN PEREZ GARCIA",
        "numero_de_contrato": "CONT-001",
        "valor_sancion": "5000000",
        "fecha_de_publicacion": "2020-01-15T00:00:00.000",
        "fecha_de_firmeza": "2020-02-01T00:00:00.000",
        "fecha_de_cargue": "2020-01-20T00:00:00.000",
        "ruta_de_proceso": "https://example.com/proceso",
    }
    defaults.update(kwargs)
    return defaults


def _make_empresa_row(**kwargs):
    """Build a multas row for an empresa contractor."""
    defaults = _make_row(
        documento_contratista="890399010",
        nombre_contratista="CONSTRUCTORA LTDA",
    )
    defaults.update(kwargs)
    return defaults


def _make_df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


class TestClassifyContratistaTipo:
    """classify_contratista_type() classifies based on name heuristics."""

    def test_sas_suffix_empresa(self):
        assert classify_contratista_type("CONSORCIO EJEMPLO S.A.S") == "empresa"

    def test_ltda_suffix_empresa(self):
        assert classify_contratista_type("CONSTRUCTORA LTDA") == "empresa"

    def test_consorcio_empresa(self):
        assert classify_contratista_type("CONSORCIO VIAS Y PUENTES") == "empresa"

    def test_union_temporal_empresa(self):
        assert classify_contratista_type("UNION TEMPORAL SALUD 2020") == "empresa"

    def test_sa_suffix_empresa(self):
        assert classify_contratista_type("EMPRESA SERVICIOS S.A") == "empresa"

    def test_natural_name_persona(self):
        assert classify_contratista_type("JUAN CARLOS PEREZ") == "persona"

    def test_none_desconocido(self):
        assert classify_contratista_type(None) == "desconocido"

    def test_empty_string_desconocido(self):
        assert classify_contratista_type("") == "desconocido"

    def test_case_insensitive(self):
        """Lowercase 'ltda' should match too."""
        assert classify_contratista_type("constructora ltda") == "empresa"


class TestTransformIdSancion:
    """transform() builds composite id_sancion correctly."""

    def test_composite_id_from_nit_resolucion_doc(self, pipeline):
        """id_sancion = f"{normalize_nit(nit_entidad)}_{numero_resolucion}_{doc_clean}"."""
        df = _make_df([_make_row(
            nit_entidad="890000858-1",  # check digit stripped -> "890000858"
            numero_de_resolucion="RES-001",
            documento_contratista="12345678",
        )])
        records = pipeline.transform(df)
        assert len(records) == 1
        # nit normalized: "890000858-1" -> "890000858"
        assert records[0]["id_sancion"].startswith("890000858_RES-001_")

    def test_skip_when_numero_resolucion_missing(self, pipeline):
        df = _make_df([_make_row(numero_de_resolucion="")])
        records = pipeline.transform(df)
        assert records == []

    def test_skip_when_numero_resolucion_none(self, pipeline):
        row = _make_row()
        del row["numero_de_resolucion"]
        df = _make_df([row])
        records = pipeline.transform(df)
        assert records == []


class TestTransformNitNormalization:
    """normalize_nit() called on nit_entidad (handles check digit)."""

    def test_nit_entidad_check_digit_stripped(self, pipeline):
        df = _make_df([_make_row(nit_entidad="890000858-1")])
        records = pipeline.transform(df)
        assert records[0]["nit_entidad"] == "890000858"

    def test_nit_entidad_without_check_digit(self, pipeline):
        df = _make_df([_make_row(nit_entidad="900185212")])
        records = pipeline.transform(df)
        assert records[0]["nit_entidad"] == "900185212"

    def test_documento_contratista_normalized_for_persona(self, pipeline):
        """normalize_nit() applied to documento_contratista for persona path."""
        df = _make_df([_make_row(
            documento_contratista="079123456",  # leading zero stripped
            nombre_contratista="JUAN PEREZ",
        )])
        records = pipeline.transform(df)
        assert records[0]["cedula_contratista"] == "79123456"

    def test_documento_contratista_normalized_for_empresa(self, pipeline):
        """normalize_nit() applied to documento_contratista for empresa path."""
        df = _make_df([_make_row(
            documento_contratista="890399010-4",  # check digit stripped
            nombre_contratista="CONSTRUCTORA LTDA",
        )])
        records = pipeline.transform(df)
        assert records[0]["nit_contratista"] == "890399010"


class TestTransformContratistaPaths:
    """transform() routes to empresa or persona based on name classification."""

    def test_empresa_record_has_nit_contratista_not_cedula(self, pipeline):
        df = _make_df([_make_empresa_row()])
        records = pipeline.transform(df)
        assert records[0]["contratista_type"] == "empresa"
        assert records[0]["nit_contratista"] is not None
        assert records[0]["cedula_contratista"] is None

    def test_persona_record_has_cedula_not_nit(self, pipeline):
        df = _make_df([_make_row(
            documento_contratista="12345678",
            nombre_contratista="JUAN PEREZ GARCIA",
        )])
        records = pipeline.transform(df)
        assert records[0]["contratista_type"] == "persona"
        assert records[0]["cedula_contratista"] is not None
        assert records[0]["nit_contratista"] is None

    def test_fuente_is_dataset_id(self, pipeline):
        df = _make_df([_make_row()])
        records = pipeline.transform(df)
        assert records[0]["fuente"] == "4n4q-k399"

    def test_valor_sancion_parsed_as_float(self, pipeline):
        df = _make_df([_make_row(valor_sancion="5000000")])
        records = pipeline.transform(df)
        assert records[0]["valor_sancion"] == 5000000.0

    def test_ingested_at_is_set(self, pipeline):
        df = _make_df([_make_row()])
        records = pipeline.transform(df)
        assert "ingested_at" in records[0]
        assert records[0]["ingested_at"]


class TestLoadThreePasses:
    """load() must execute exactly 3 merge_batch() calls."""

    @pytest.mark.asyncio
    async def test_load_calls_merge_batch_three_times(self, pipeline):
        loader = MagicMock()
        loader.merge_batch = AsyncMock(return_value=1)

        # Mix of persona and empresa records
        records = [
            {
                "id_sancion": "S1", "nit_entidad": "890000858",
                "nombre_entidad": "MINISTERIO", "nivel": "NACIONAL", "orden": "ADMIN",
                "municipio": "BOGOTA", "numero_resolucion": "RES-001",
                "numero_contrato": "C001", "valor_sancion": 5000000.0,
                "fecha_publicacion": None, "fecha_firmeza": None, "fecha_cargue": None,
                "url_fuente": None, "fuente": "4n4q-k399", "ingested_at": "2026-01-01T00:00:00Z",
                "nombre_contratista": "CONSTRUCTORA LTDA",
                "contratista_type": "empresa", "nit_contratista": "890399010",
                "cedula_contratista": None,
            },
            {
                "id_sancion": "S2", "nit_entidad": "890000858",
                "nombre_entidad": "MINISTERIO", "nivel": "NACIONAL", "orden": "ADMIN",
                "municipio": "BOGOTA", "numero_resolucion": "RES-002",
                "numero_contrato": "C002", "valor_sancion": 1000000.0,
                "fecha_publicacion": None, "fecha_firmeza": None, "fecha_cargue": None,
                "url_fuente": None, "fuente": "4n4q-k399", "ingested_at": "2026-01-01T00:00:00Z",
                "nombre_contratista": "JUAN PEREZ",
                "contratista_type": "persona", "nit_contratista": None,
                "cedula_contratista": "12345678",
            },
        ]

        await pipeline.load(records, loader)
        assert loader.merge_batch.call_count == 3


class TestCypherStructure:
    """Verify Cypher constants have required patterns."""

    def test_sancion_entidad_cypher_has_impuso(self):
        from etl.sources.secop_multas import CYPHER_SANCION_ENTIDAD
        assert "IMPUSO" in CYPHER_SANCION_ENTIDAD

    def test_empresa_cypher_has_multado(self):
        from etl.sources.secop_multas import CYPHER_EMPRESA_MULTADO
        assert "MULTADO" in CYPHER_EMPRESA_MULTADO

    def test_persona_cypher_has_multado(self):
        from etl.sources.secop_multas import CYPHER_PERSONA_MULTADO
        assert "MULTADO" in CYPHER_PERSONA_MULTADO

    def test_sancion_merge_on_id_sancion(self):
        from etl.sources.secop_multas import CYPHER_SANCION_ENTIDAD
        assert "MERGE (s:Sancion {id_sancion: row.id_sancion})" in CYPHER_SANCION_ENTIDAD

    def test_empresa_merge_on_nit(self):
        from etl.sources.secop_multas import CYPHER_EMPRESA_MULTADO
        assert "MERGE (e:Empresa {nit: row.nit_contratista})" in CYPHER_EMPRESA_MULTADO

    def test_persona_merge_on_cedula(self):
        from etl.sources.secop_multas import CYPHER_PERSONA_MULTADO
        assert "MERGE (p:Persona {cedula: row.cedula_contratista})" in CYPHER_PERSONA_MULTADO
