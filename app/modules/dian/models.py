"""Catálogos de la DIAN (tarea A1): países, departamentos, municipios y tipos de
identificación, tal como los piden los formatos de información exógena.

Fuente: anexos técnicos de información exógena de la DIAN (hoy, Resolución 000227 de 2025).

- Son de la plataforma, no de una organización: no llevan organization_id.
- Los códigos son texto: así se conservan los ceros a la izquierda ("05" Antioquia).
- Vigencia por año gravable: cuando la DIAN publica una lista nueva, las filas de la
  anterior se cierran con year_to y se cargan las nuevas con su year_from. year_to vacío
  = vigente.
"""

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field

from app.shared.models import BaseTable


def _validity(table: str) -> tuple:
    """Lo común a los cuatro catálogos: el código no se repite dentro de una misma lista
    (mismo año de inicio) y los años de vigencia tienen sentido."""
    return (
        Index(
            f"ux_{table}_code_year_from",
            "code",
            "year_from",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("year_from BETWEEN 1990 AND 2100", name="year_from_range"),
        CheckConstraint("year_to IS NULL OR year_to >= year_from", name="year_to_after_from"),
    )


class Country(BaseTable):
    """País, con el código de tres dígitos de la DIAN (169 = Colombia)."""

    __tablename__ = "countries"
    __table_args__ = (
        *_validity("countries"),
        CheckConstraint("code ~ '^[0-9]{3}$'", name="code_digits"),
    )

    code: str = Field(max_length=3)
    name: str = Field(max_length=150)
    year_from: int = Field(description="Primer año gravable en que rige")
    year_to: int | None = Field(default=None, description="Último año gravable; vacío = vigente")


class Department(BaseTable):
    """Departamento, con el código DANE de dos dígitos (05 = Antioquia)."""

    __tablename__ = "departments"
    __table_args__ = (
        *_validity("departments"),
        CheckConstraint("code ~ '^[0-9]{2}$'", name="code_digits"),
    )

    code: str = Field(max_length=2)
    name: str = Field(max_length=150)
    year_from: int = Field(description="Primer año gravable en que rige")
    year_to: int | None = Field(default=None, description="Último año gravable; vacío = vigente")


class Municipality(BaseTable):
    """Municipio, con el código DANE de cinco dígitos (05001 = Medellín). Los dos primeros
    son el de su departamento. Sin FK a departments: un código de departamento puede
    estar en varias listas (una por vigencia)."""

    __tablename__ = "municipalities"
    __table_args__ = (
        *_validity("municipalities"),
        CheckConstraint("code ~ '^[0-9]{5}$'", name="code_digits"),
        CheckConstraint("department_code = left(code, 2)", name="department_code_matches"),
    )

    code: str = Field(max_length=5)
    department_code: str = Field(max_length=2, index=True)
    name: str = Field(max_length=150)
    year_from: int = Field(description="Primer año gravable en que rige")
    year_to: int | None = Field(default=None, description="Último año gravable; vacío = vigente")


class IdentificationType(BaseTable):
    """Con qué se identifica un tercero (13 = cédula de ciudadanía, 31 = NIT). No es el
    tipo de documento que se carga (RUT, declaración…): ese es otro catálogo."""

    __tablename__ = "identification_types"
    __table_args__ = (
        *_validity("identification_types"),
        CheckConstraint("code ~ '^[0-9]{2}$'", name="code_digits"),
    )

    code: str = Field(max_length=2)
    name: str = Field(max_length=150)
    usage: str | None = Field(default=None, max_length=250, description="Uso")
    year_from: int = Field(description="Primer año gravable en que rige")
    year_to: int | None = Field(default=None, description="Último año gravable; vacío = vigente")
