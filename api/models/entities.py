"""Pydantic response models for HunterLeech entity types."""
from datetime import datetime
from pydantic import BaseModel


class EmpresaDTO(BaseModel):
    nit: str
    razon_social: str | None = None
    tipo: str | None = None
    municipio: str | None = None
    fecha_constitucion: str | None = None
    fuente: str | None = None
    ingested_at: datetime | None = None


class PersonaDTO(BaseModel):
    cedula: str
    nombre: str | None = None
    cargo: str | None = None
    # Protected fields only present when PUBLIC_MODE=false
    email: str | None = None
    telefono_personal: str | None = None
    direccion_residencia: str | None = None


class EntidadPublicaDTO(BaseModel):
    codigo_entidad: str
    nombre: str | None = None
    nivel: str | None = None
    sector: str | None = None


class ContratoDTO(BaseModel):
    id_contrato: str
    objeto: str | None = None
    valor: float | None = None
    fecha_inicio: str | None = None
    fecha_fin: str | None = None
    modalidad: str | None = None
    fuente: str | None = None


class SancionDTO(BaseModel):
    id_sancion: str
    tipo: str | None = None
    fecha: str | None = None
    autoridad: str | None = None
    descripcion: str | None = None
    fuente: str | None = None
