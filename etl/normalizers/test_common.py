import pytest
from etl.normalizers.common import (
    normalize_nit,
    normalize_cedula,
    normalize_razon_social,
    classify_proveedor_type,
)


class TestNormalizeNit:
    def test_strips_check_digit_after_hyphen(self):
        assert normalize_nit("890399010-4") == "890399010"

    def test_strips_leading_zeros(self):
        assert normalize_nit("0890399010") == "890399010"

    def test_strips_dots(self):
        assert normalize_nit("890.399.010") == "890399010"

    def test_strips_spaces(self):
        assert normalize_nit("890 399 010") == "890399010"

    def test_empty_string_returns_none(self):
        assert normalize_nit("") is None

    def test_none_returns_none(self):
        assert normalize_nit(None) is None

    def test_na_returns_none(self):
        assert normalize_nit("N/A") is None

    def test_alphanumeric_returns_none(self):
        assert normalize_nit("ABC123") is None

    def test_single_zero_after_strip_returns_none(self):
        assert normalize_nit("0") is None


class TestNormalizeCedula:
    def test_strips_leading_zeros(self):
        assert normalize_cedula("079123456") == "79123456"

    def test_none_returns_none(self):
        assert normalize_cedula(None) is None

    def test_empty_returns_none(self):
        assert normalize_cedula("") is None


class TestNormalizeRazonSocial:
    def test_removes_sas_suffix(self):
        assert normalize_razon_social("CONSTRUCCIONES S.A.S.") == "construcciones"

    def test_removes_ltda_suffix(self):
        assert normalize_razon_social("Empresa Ltda.") == "empresa"

    def test_collapses_whitespace(self):
        assert normalize_razon_social("  Empresa  ABC  ") == "empresa abc"

    def test_strips_accents_and_suffix(self):
        assert normalize_razon_social("Construcción S.A.") == "construccion"

    def test_none_returns_none(self):
        assert normalize_razon_social(None) is None


class TestClassifyProveedorType:
    def test_nit_is_empresa(self):
        assert classify_proveedor_type("12345678", "Nit") == "empresa"

    def test_nit_persona_natural_is_persona(self):
        assert classify_proveedor_type("12345678", "Nit de Persona Natural") == "persona"

    def test_cedula_ciudadania_is_persona(self):
        assert classify_proveedor_type("12345678", "Cedula de Ciudadania") == "persona"

    def test_cedula_extranjeria_is_persona(self):
        assert classify_proveedor_type("12345678", "Cedula de Extranjeria") == "persona"

    def test_none_tipo_is_desconocido(self):
        assert classify_proveedor_type("12345678", None) == "desconocido"

    def test_empty_tipo_is_desconocido(self):
        assert classify_proveedor_type("12345678", "") == "desconocido"
