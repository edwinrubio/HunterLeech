"""
Canonical identifier normalization for HunterLeech ETL pipelines.

This module is the single source of truth for NIT and cedula normalization.
ALL pipelines must import from here. Never normalize inline in source-specific files.

Design decisions:
- normalize_nit() and normalize_cedula() return None for unresolvable identifiers.
  Do NOT store empty string or "N/A" as NIT in Neo4j — these create false uniqueness
  collisions via MERGE. Log skipped records for monitoring.
- The MERGE key for Contrato uses a composite: numero_del_contrato + "_" + origen
  to scope identifiers to their source system (SECOPI vs SECOPII).
"""

import re
import unicodedata
from typing import Literal


def normalize_nit(raw: str | None) -> str | None:
    """
    Normalize NIT to canonical form: digits only, no leading zeros, no check digit.

    Returns None for empty or non-normalizable input.
    Callers MUST handle None: skip the record, do not attempt MERGE with null NIT.

    Examples:
        "890399010-4"  -> "890399010"
        "0890399010"   -> "890399010"
        "890.399.010"  -> "890399010"
        ""             -> None
        "N/A"          -> None
    """
    if not raw or not isinstance(raw, str):
        return None
    # Strip check digit: if hyphen present, everything after last hyphen is the check digit
    stripped = raw.strip()
    if '-' in stripped:
        stripped = stripped.rsplit('-', 1)[0]
    # Strip remaining dots and spaces
    cleaned = re.sub(r'[\s.]', '', stripped)
    # Remove leading zeros
    cleaned = cleaned.lstrip('0')
    # Must be non-empty and all-numeric after cleaning
    if not cleaned or not cleaned.isdigit():
        return None
    return cleaned


def normalize_cedula(raw: str | None) -> str | None:
    """
    Normalize cedula to digits only, no leading zeros.
    Cedulas have no check digit — same stripping logic as NIT.
    """
    return normalize_nit(raw)


def normalize_razon_social(raw: str | None) -> str | None:
    """
    Produce a deduplication key from a company name.
    Lowercased, accent-stripped, legal suffix removed, whitespace collapsed.

    This is NOT the display name — it is used as a secondary matching signal
    when NIT is missing. Never store this key as the razon_social property.

    Examples:
        "CONSTRUCCIONES S.A.S." -> "construcciones"
        "Empresa Ltda."         -> "empresa"
        "Construccion S.A."     -> "construccion"
    """
    if not raw:
        return None

    # Lowercase
    text = raw.lower()

    # Strip combining characters (accents)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    # Remove legal suffixes (longest first to avoid partial matches)
    suffixes = [
        's.a.s.', 's. a. s.', 'sas',
        's.a.', 's. a.',
        'ltda.', 'ltda',
        's.c.a.', 'sca',
        'e.u.',
        's.e.m.',
        'eu',
    ]
    for suffix in suffixes:
        # Remove as trailing word with optional trailing punctuation
        text = re.sub(r'\s*' + re.escape(suffix) + r'\s*$', '', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text if text else None


ProveedorType = Literal["empresa", "persona", "desconocido"]

# Document types that indicate a natural person (not a legal entity)
_PERSONA_TIPO_KEYWORDS = {
    "nit de persona natural",
    "cedula de ciudadania",
    "cedula de extranjeria",
    "pasaporte",
    "tarjeta de identidad",
}


def classify_proveedor_type(
    documento: str | None,
    tipo_documento: str | None,
) -> ProveedorType:
    """
    Determine whether a SECOP contractor is a legal entity (empresa) or
    natural person (persona) based on the tipo_documento_proveedor field.

    This classification controls:
    - Which Neo4j label to use in MERGE: :Empresa vs :Persona
    - How documento_proveedor is treated under PUBLIC_MODE=true

    Returns:
        "empresa"      — NIT belonging to a legal entity
        "persona"      — cedula or NIT-de-persona-natural; SEMIPRIVADA in PUBLIC_MODE
        "desconocido"  — tipo_documento absent or unrecognized; log and skip MERGE
    """
    if not tipo_documento or not isinstance(tipo_documento, str):
        return "desconocido"

    normalized_tipo = tipo_documento.strip().lower()

    if not normalized_tipo:
        return "desconocido"

    # Strip combining characters (accents) so "Cédula de Ciudadanía" matches "cedula de ciudadania".
    # SECOP II uses accented values; SECOP I may not — accent-normalizing here handles both.
    normalized_tipo = unicodedata.normalize("NFD", normalized_tipo)
    normalized_tipo = "".join(c for c in normalized_tipo if unicodedata.category(c) != "Mn")

    # Natural person check
    for keyword in _PERSONA_TIPO_KEYWORDS:
        if keyword in normalized_tipo:
            return "persona"

    # Plain NIT without "persona natural" qualifier -> legal entity
    if "nit" in normalized_tipo:
        return "empresa"

    return "desconocido"
