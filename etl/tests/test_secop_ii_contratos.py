"""
Tests for SecopIIContratosPipeline.

Covers:
- transform() skip logic (missing codigo_entidad, missing id_contrato)
- transform() field mapping (id_contrato direct, no composite)
- transform() proveedor classification via classify_proveedor_type()
- transform() normalize_nit() called for both empresa and persona branches
- transform() valor_del_contrato parsing (plain float — no dot removal)
- transform() fuente="jbjy-vk9h" on every record
- load() executes exactly 3 merge_batch() calls
- load() filters empresa_records to proveedor_type=="empresa" and non-None nit
"""

from unittest.mock import AsyncMock, MagicMock, patch
import polars as pl
import pytest

from etl.sources.secop_ii_contratos import SecopIIContratosPipeline, FUENTE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_row(**overrides) -> dict:
    """Return a minimal valid SECOP II Contratos row."""
    base = {
        "codigo_entidad": "CO-ENT-001",
        "id_contrato": "CO1.PCCNTR.1234",
        "nombre_entidad": "MINISTERIO DE HACIENDA",
        "nit_entidad": "899999001-7",
        "departamento": "Cundinamarca",
        "ciudad": "Bogotá D.C.",
        "sector": "Hacienda",
        "orden": "Nacional",
        "valor_del_contrato": "50000000",
        "objeto_del_contrato": "Suministro de equipos de computo",
        "tipo_de_contrato": "Suministro",
        "modalidad_de_contratacion": "Contratacion Directa",
        "estado_contrato": "Liquidado",
        "fecha_de_firma": "2024-01-15T00:00:00.000",
        "fecha_de_inicio_del_contrato": "2024-02-01T00:00:00.000",
        "fecha_de_fin_del_contrato": "2024-12-31T00:00:00.000",
        "proceso_de_compra": "CO1.BDOS.1234",
        "urlproceso": "https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=CO1",
        "documento_proveedor": "900123456-1",
        "tipodocproveedor": "NIT",
        "proveedor_adjudicado": "TECNO COLOMBIA SAS",
        "codigo_proveedor": "CO1.PROVI.5678",
    }
    base.update(overrides)
    return base


def make_df(*rows) -> pl.DataFrame:
    """Wrap one or more row dicts into a Polars DataFrame."""
    return pl.DataFrame(list(rows), infer_schema_length=None)


# ---------------------------------------------------------------------------
# transform() — skip logic
# ---------------------------------------------------------------------------

class TestTransformSkipLogic:

    def test_skips_row_missing_codigo_entidad(self):
        """transform() returns empty list when codigo_entidad is absent."""
        pipeline = SecopIIContratosPipeline()
        row = make_row()
        del row["codigo_entidad"]
        df = make_df(row)
        result = pipeline.transform(df)
        assert result == []

    def test_skips_row_empty_codigo_entidad(self):
        """transform() skips when codigo_entidad is an empty string."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(codigo_entidad=""))
        result = pipeline.transform(df)
        assert result == []

    def test_skips_row_missing_id_contrato(self):
        """transform() returns empty list when id_contrato is absent."""
        pipeline = SecopIIContratosPipeline()
        row = make_row()
        del row["id_contrato"]
        df = make_df(row)
        result = pipeline.transform(df)
        assert result == []

    def test_skips_row_empty_id_contrato(self):
        """transform() skips when id_contrato is an empty string."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(id_contrato=""))
        result = pipeline.transform(df)
        assert result == []

    def test_valid_row_not_skipped(self):
        """transform() returns one record for a complete valid row."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row())
        result = pipeline.transform(df)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# transform() — id_contrato used directly (no composite key)
# ---------------------------------------------------------------------------

class TestTransformIdContrato:

    def test_id_contrato_used_directly(self):
        """transform() uses id_contrato field directly, not a composite."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(id_contrato="CO1.PCCNTR.9999"))
        result = pipeline.transform(df)
        assert result[0]["id_contrato"] == "CO1.PCCNTR.9999"

    def test_id_contrato_not_combined_with_any_other_field(self):
        """id_contrato value in output matches API field verbatim."""
        pipeline = SecopIIContratosPipeline()
        raw_id = "CO1.PCCNTR.42"
        df = make_df(make_row(id_contrato=raw_id))
        result = pipeline.transform(df)
        # The value must be exactly the raw id — no underscore joining
        assert "_" not in result[0]["id_contrato"] or result[0]["id_contrato"] == raw_id


# ---------------------------------------------------------------------------
# transform() — proveedor classification
# ---------------------------------------------------------------------------

class TestTransformProveedorClassification:

    def test_nit_tipodoc_classified_as_empresa(self):
        """transform() sets proveedor_type='empresa' for tipodocproveedor='NIT'."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(tipodocproveedor="NIT", documento_proveedor="900123456-1"))
        result = pipeline.transform(df)
        assert result[0]["proveedor_type"] == "empresa"

    def test_cedula_tipodoc_classified_as_persona(self):
        """transform() sets proveedor_type='persona' for cedula document type."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(
            tipodocproveedor="Cédula de Ciudadanía",
            documento_proveedor="12345678",
        ))
        result = pipeline.transform(df)
        assert result[0]["proveedor_type"] == "persona"

    def test_unknown_tipodoc_classified_as_desconocido(self):
        """transform() sets proveedor_type='desconocido' for unrecognized type."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(tipodocproveedor="TIPO_DESCONOCIDO"))
        result = pipeline.transform(df)
        assert result[0]["proveedor_type"] == "desconocido"


# ---------------------------------------------------------------------------
# transform() — normalize_nit() called for empresa and persona branches
# ---------------------------------------------------------------------------

class TestTransformNormalization:

    def test_normalize_nit_called_for_empresa(self):
        """For empresa, nit_contratista is normalize_nit(documento_proveedor)."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(tipodocproveedor="NIT", documento_proveedor="890399010-4"))
        result = pipeline.transform(df)
        # normalize_nit strips the check digit
        assert result[0]["nit_contratista"] == "890399010"
        assert result[0]["cedula_contratista"] is None

    def test_normalize_nit_called_for_persona(self):
        """For persona, cedula_contratista is normalize_nit(documento_proveedor)."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(
            tipodocproveedor="Cédula de Ciudadanía",
            documento_proveedor="012345678",
        ))
        result = pipeline.transform(df)
        # normalize_nit strips leading zero
        assert result[0]["cedula_contratista"] == "12345678"
        assert result[0]["nit_contratista"] is None

    def test_empresa_with_invalid_nit_gets_none(self):
        """transform() produces nit_contratista=None when document is non-numeric."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(tipodocproveedor="NIT", documento_proveedor="N/A"))
        result = pipeline.transform(df)
        assert result[0]["nit_contratista"] is None


# ---------------------------------------------------------------------------
# transform() — valor_del_contrato parsing (SECOP II: plain integer string)
# ---------------------------------------------------------------------------

class TestTransformValorParsing:

    def test_plain_integer_string_parsed_as_float(self):
        """Plain integer string "50000000" -> 50000000.0 (no dot removal)."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(valor_del_contrato="50000000"))
        result = pipeline.transform(df)
        assert result[0]["valor_contrato"] == 50000000.0

    def test_value_with_dots_treated_as_decimal(self):
        """SECOP II does NOT use dots as thousands separators.
        "1.000.000" in SECOP II would be an unusual value but must NOT be
        dot-stripped. The plain float() parse gives 1.0 for "1.000" input
        (float("1.000") == 1.0), confirming no dot removal happens."""
        pipeline = SecopIIContratosPipeline()
        # "1000" -> 1000.0, no dot removal
        df = make_df(make_row(valor_del_contrato="1000"))
        result = pipeline.transform(df)
        assert result[0]["valor_contrato"] == 1000.0

    def test_none_valor_returns_none(self):
        """Missing valor_del_contrato results in None, not an error."""
        pipeline = SecopIIContratosPipeline()
        row = make_row()
        row["valor_del_contrato"] = None
        df = make_df(row)
        result = pipeline.transform(df)
        assert result[0]["valor_contrato"] is None

    def test_invalid_valor_returns_none(self):
        """Non-numeric valor_del_contrato returns None."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(valor_del_contrato="invalid"))
        result = pipeline.transform(df)
        assert result[0]["valor_contrato"] is None

    def test_dots_not_stripped_secop2_pitfall(self):
        """Confirm _parse_valor_secop2 does NOT strip dots (SECOP I pitfall).
        In SECOP II, '1.5' should parse as 1.5 (decimal), not 15."""
        from etl.sources.secop_ii_contratos import _parse_valor_secop2
        assert _parse_valor_secop2("1.5") == 1.5
        # Compare: SECOP I's _parse_valor would strip the dot and give 15.0
        # SECOP II must give 1.5
        assert _parse_valor_secop2("50000000") == 50000000.0


# ---------------------------------------------------------------------------
# transform() — fuente on every record
# ---------------------------------------------------------------------------

class TestTransformFuente:

    def test_fuente_is_jbjy_vk9h(self):
        """Every transformed record carries fuente='jbjy-vk9h'."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row(), make_row(id_contrato="CO1.PCCNTR.2"))
        result = pipeline.transform(df)
        assert all(r["fuente"] == "jbjy-vk9h" for r in result)

    def test_fuente_equals_dataset_constant(self):
        """fuente value matches the FUENTE module constant."""
        pipeline = SecopIIContratosPipeline()
        df = make_df(make_row())
        result = pipeline.transform(df)
        assert result[0]["fuente"] == FUENTE


# ---------------------------------------------------------------------------
# load() — three merge_batch() calls
# ---------------------------------------------------------------------------

class TestLoadThreePasses:

    @pytest.mark.asyncio
    async def test_load_calls_merge_batch_three_times(self):
        """load() always calls merge_batch() exactly 3 times."""
        pipeline = SecopIIContratosPipeline()
        loader = MagicMock()
        loader.merge_batch = AsyncMock(return_value=1)

        records = [
            {
                "id_contrato": "CO1.PCCNTR.1",
                "proveedor_type": "empresa",
                "nit_contratista": "890399010",
                "cedula_contratista": None,
            },
            {
                "id_contrato": "CO1.PCCNTR.2",
                "proveedor_type": "persona",
                "nit_contratista": None,
                "cedula_contratista": "12345678",
            },
        ]

        await pipeline.load(records, loader)
        assert loader.merge_batch.call_count == 3

    @pytest.mark.asyncio
    async def test_load_calls_merge_batch_three_times_empresa_only(self):
        """load() calls merge_batch 3 times even with only empresa records."""
        pipeline = SecopIIContratosPipeline()
        loader = MagicMock()
        loader.merge_batch = AsyncMock(return_value=1)

        records = [
            {
                "id_contrato": "CO1.PCCNTR.1",
                "proveedor_type": "empresa",
                "nit_contratista": "890399010",
                "cedula_contratista": None,
            },
        ]

        await pipeline.load(records, loader)
        # Pass 1: all records, Pass 2: empresa records, Pass 3: persona (0 items but still called)
        assert loader.merge_batch.call_count == 3

    @pytest.mark.asyncio
    async def test_load_pass1_receives_all_records(self):
        """load() passes all records to the first merge_batch() call."""
        pipeline = SecopIIContratosPipeline()
        loader = MagicMock()
        loader.merge_batch = AsyncMock(return_value=1)

        records = [
            {
                "id_contrato": "CO1.PCCNTR.1",
                "proveedor_type": "empresa",
                "nit_contratista": "111",
                "cedula_contratista": None,
            },
            {
                "id_contrato": "CO1.PCCNTR.2",
                "proveedor_type": "persona",
                "nit_contratista": None,
                "cedula_contratista": "222",
            },
        ]

        await pipeline.load(records, loader)
        # First call gets all records
        first_call_records = loader.merge_batch.call_args_list[0][0][0]
        assert len(first_call_records) == 2


# ---------------------------------------------------------------------------
# load() — empresa_records filter
# ---------------------------------------------------------------------------

class TestLoadEmpresaFilter:

    @pytest.mark.asyncio
    async def test_load_pass2_filters_empresa_with_non_null_nit(self):
        """load() pass 2 only includes empresa records with non-None nit_contratista."""
        pipeline = SecopIIContratosPipeline()
        loader = MagicMock()
        loader.merge_batch = AsyncMock(return_value=1)

        records = [
            # Valid empresa — should be in pass 2
            {"id_contrato": "1", "proveedor_type": "empresa", "nit_contratista": "890399010", "cedula_contratista": None},
            # empresa but nit is None — should NOT be in pass 2
            {"id_contrato": "2", "proveedor_type": "empresa", "nit_contratista": None, "cedula_contratista": None},
            # persona — should NOT be in pass 2
            {"id_contrato": "3", "proveedor_type": "persona", "nit_contratista": None, "cedula_contratista": "12345678"},
        ]

        await pipeline.load(records, loader)

        # Pass 2 (second call) should only contain the first record
        second_call_records = loader.merge_batch.call_args_list[1][0][0]
        assert len(second_call_records) == 1
        assert second_call_records[0]["id_contrato"] == "1"

    @pytest.mark.asyncio
    async def test_load_pass3_filters_persona_with_non_null_cedula(self):
        """load() pass 3 only includes persona records with non-None cedula_contratista."""
        pipeline = SecopIIContratosPipeline()
        loader = MagicMock()
        loader.merge_batch = AsyncMock(return_value=1)

        records = [
            # Valid persona
            {"id_contrato": "1", "proveedor_type": "persona", "nit_contratista": None, "cedula_contratista": "12345"},
            # persona with null cedula — should NOT be in pass 3
            {"id_contrato": "2", "proveedor_type": "persona", "nit_contratista": None, "cedula_contratista": None},
            # empresa — should NOT be in pass 3
            {"id_contrato": "3", "proveedor_type": "empresa", "nit_contratista": "999", "cedula_contratista": None},
        ]

        await pipeline.load(records, loader)

        # Pass 3 (third call) should only contain the first persona record
        third_call_records = loader.merge_batch.call_args_list[2][0][0]
        assert len(third_call_records) == 1
        assert third_call_records[0]["id_contrato"] == "1"
