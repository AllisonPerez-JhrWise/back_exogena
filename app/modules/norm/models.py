"""La norma (tarea A1): catálogos, iguales para todas las firmas. Ninguna tabla guarda
datos de un cliente: lo de cada cliente (su RUT, sus declaraciones) vive en extracción y
se le consulta.

- El valor de la UVT por año y los topes que deciden si un cliente debe presentar
  exógena. Los topes se guardan en UVT; el valor en pesos no se guarda: se calcula cada
  vez con la UVT del año gravable que se revisa.
- El diccionario de las casillas del RUT que usan las reglas y de sus códigos.
- Los formatos de exógena y sus conceptos.

Es de la plataforma, no de una organización: no lleva organization_id.
"""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Index, text
from sqlmodel import Field

from app.shared.models import DB_SCHEMA, BaseTable


class ThresholdAppliesTo(StrEnum):
    """A quién aplica un tope. Se guarda el código; el front muestra la etiqueta."""

    LEGAL_ENTITY = "legal_entity"  # Persona jurídica
    NATURAL_PERSON = "natural_person"  # Persona natural
    ANY = "any"  # Cualquiera


class UvtValue(BaseTable):
    """Cuánto vale 1 UVT en pesos en un año, según la resolución de la DIAN."""

    __tablename__ = "uvt_values"
    __table_args__ = (
        # Un solo valor por año
        Index("ux_uvt_values_year", "year", unique=True, postgresql_where=text("NOT is_deleted")),
        CheckConstraint("year BETWEEN 2000 AND 2100", name="year_range"),
        CheckConstraint("value > 0", name="value_positive"),
    )

    year: int = Field(description="Año en que rige")
    # Entero en pesos (regla del acuerdo)
    value: int = Field(sa_type=BigInteger, description="Valor de 1 UVT en pesos")
    resolution: str = Field(max_length=250, description="Resolución de la DIAN que lo fija")
    norm_url: str | None = Field(default=None, max_length=500, description="Enlace a la norma")


class Threshold(BaseTable):
    """Un tope en UVT (p. ej. 2.400 UVT de ingresos brutos para persona jurídica), con su
    vigencia por año gravable: si la norma cambia, el tope viejo se cierra con year_to y
    se carga el nuevo."""

    __tablename__ = "thresholds"
    __table_args__ = (
        # El mismo tope no se repite en una misma vigencia
        Index(
            "ux_thresholds_code_year_from",
            "code",
            "year_from",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint(
            "applies_to IN ('legal_entity', 'natural_person', 'any')", name="applies_to_valid"
        ),
        CheckConstraint("value_uvt > 0", name="value_uvt_positive"),
        CheckConstraint("year_from BETWEEN 2000 AND 2100", name="year_from_range"),
        CheckConstraint("year_to IS NULL OR year_to >= year_from", name="year_to_after_from"),
    )

    # Código para que las reglas lo encuentren (en inglés, snake_case)
    code: str = Field(max_length=60)
    name: str = Field(max_length=250)
    value_uvt: int = Field(description="Tope en UVT")
    applies_to: str = Field(max_length=20)
    year_from: int = Field(description="Primer año gravable en que rige")
    year_to: int | None = Field(default=None, description="Último año gravable; vacío = vigente")
    norm: str | None = Field(default=None, max_length=250, description="Artículo o norma")
    norm_url: str | None = Field(default=None, max_length=500, description="Enlace a la norma")


class RutBox(BaseTable):
    """Una casilla del RUT que usan las reglas y para qué (p. ej. la 53, Responsabilidades,
    dice si el cliente es responsable de IVA). Es el diccionario: lo que dice el RUT de
    cada cliente se le pide a extracción."""

    __tablename__ = "rut_boxes"
    __table_args__ = (
        Index(
            "ux_rut_boxes_box_code",
            "box_code",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("box_code ~ '^[0-9]{1,3}$'", name="box_code_digits"),
    )

    box_code: str = Field(max_length=3, description="Número de la casilla")
    name: str = Field(max_length=250)
    description: str | None = Field(default=None, max_length=1000)
    used_by_rule: str | None = Field(default=None, max_length=250, description="Qué regla la usa")
    purpose: str | None = Field(default=None, max_length=500, description="Para qué sirve")


class RutBoxCode(BaseTable):
    """Qué significa cada código de una casilla del RUT (p. ej. en la 53, el 48 es IVA)."""

    __tablename__ = "rut_box_codes"
    __table_args__ = (
        Index(
            "ux_rut_box_codes_box_code",
            "rut_box_id",
            "code",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
    )

    rut_box_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.rut_boxes.id", index=True)
    # Texto: conserva los ceros a la izquierda ("05")
    code: str = Field(max_length=10)
    name: str = Field(max_length=250)


class Format(BaseTable):
    """Un formato de información exógena (p. ej. 1001, pagos o abonos en cuenta). Una
    versión nueva de la DIAN es otra fila, con su vigencia por año gravable."""

    __tablename__ = "formats"
    __table_args__ = (
        Index(
            "ux_formats_number_version",
            "number",
            "version",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("number ~ '^[0-9]{4}$'", name="number_digits"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("year_from BETWEEN 2000 AND 2100", name="year_from_range"),
        CheckConstraint("year_to IS NULL OR year_to >= year_from", name="year_to_after_from"),
    )

    number: str = Field(max_length=4, description="Número del formato")
    version: int
    name: str = Field(max_length=250)
    article: str | None = Field(default=None, max_length=100, description="Artículo de la norma")
    year_from: int = Field(description="Primer año gravable en que rige")
    year_to: int | None = Field(default=None, description="Último año gravable; vacío = vigente")


class FormatConcept(BaseTable):
    """Un concepto de un formato (p. ej. en el 1001, el 5002 son honorarios)."""

    __tablename__ = "format_concepts"
    __table_args__ = (
        Index(
            "ux_format_concepts_format_code_year_from",
            "format_id",
            "code",
            "year_from",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("year_from BETWEEN 2000 AND 2100", name="year_from_range"),
        CheckConstraint("year_to IS NULL OR year_to >= year_from", name="year_to_after_from"),
    )

    format_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.formats.id", index=True)
    code: str = Field(max_length=10)
    description: str = Field(max_length=500)
    expected_third_party: str | None = Field(
        default=None, max_length=250, description="Qué tercero se espera reportar"
    )
    year_from: int = Field(description="Primer año gravable en que rige")
    year_to: int | None = Field(default=None, description="Último año gravable; vacío = vigente")
