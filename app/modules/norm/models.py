"""La norma (tarea A1): el valor de la UVT por año y los topes que deciden si un cliente
debe presentar exógena.

Los topes se guardan en UVT. El valor en pesos no se guarda: se calcula cada vez con la
UVT del año gravable que se revisa (tope en UVT × valor de la UVT de ese año).

Es de la plataforma, no de una organización: no lleva organization_id.
"""

from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, Index, text
from sqlmodel import Field

from app.shared.models import BaseTable


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
