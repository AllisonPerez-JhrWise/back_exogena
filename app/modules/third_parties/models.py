"""Terceros: el maestro de terceros de cada cliente (tarea A1). Cada persona o empresa con
la que el cliente tuvo movimientos: proveedores, clientes, empleados…

Llave del acuerdo entre servicios: tipo de identificación + número de identificación.
El número es texto, sin puntos, comas, guiones ni espacios: así se conservan los ceros a
la izquierda (0012345 sigue siendo 0012345).

La base solo revisa el formato. Un tercero con datos incompletos (sin apellido, sin razón
social…) se guarda igual: lo detecta la revisión de exógena y lo muestra como hallazgo.

PENDIENTE (cuando exista la carga de terceros): validar que identification_type,
country_code, department_code y city_code existan en los catálogos de la DIAN vigentes
para el año gravable (app/modules/dian). No hay FK porque esos catálogos repiten el código
en cada vigencia.
"""

from uuid import UUID

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field

from app.shared.models import DB_SCHEMA, BaseTable


class ThirdParty(BaseTable):
    __tablename__ = "third_parties"
    __table_args__ = (
        # Un cliente no tiene dos veces el mismo tercero (la llave del acuerdo)
        Index(
            "ux_third_parties_company_identification",
            "company_id",
            "identification_type",
            "identification_number",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("identification_type ~ '^[0-9]{2}$'", name="identification_type_digits"),
        # Letras y números (un pasaporte puede tener letras), sin separadores
        CheckConstraint(
            "identification_number ~ '^[0-9A-Za-z]+$'", name="identification_number_clean"
        ),
        CheckConstraint("check_digit ~ '^[0-9]$'", name="check_digit_digit"),
        CheckConstraint("country_code ~ '^[0-9]{3}$'", name="country_code_digits"),
        CheckConstraint("department_code ~ '^[0-9]{2}$'", name="department_code_digits"),
        CheckConstraint("city_code ~ '^[0-9]{5}$'", name="city_code_digits"),
    )

    # La firma. ID de Identidad, sin FK
    organization_id: UUID = Field(index=True)
    company_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.companies.id", index=True)

    # Código del catálogo identification_types (13 = cédula, 31 = NIT)
    identification_type: str = Field(max_length=2)
    identification_number: str = Field(max_length=30)
    # Dígito de verificación: solo si tiene (NIT)
    check_digit: str | None = Field(default=None, max_length=1)

    # Persona natural
    first_name: str | None = Field(default=None, max_length=100)
    other_names: str | None = Field(default=None, max_length=100)
    first_last_name: str | None = Field(default=None, max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)
    # Persona jurídica
    legal_name: str | None = Field(default=None, max_length=250, description="Razón social")

    # Códigos de los catálogos de la DIAN
    country_code: str | None = Field(default=None, max_length=3)
    department_code: str | None = Field(default=None, max_length=2)
    city_code: str | None = Field(default=None, max_length=5)
    address: str | None = Field(default=None, max_length=250)
    email: str | None = Field(default=None, max_length=320)
