"""GET /api/v1/companies/{id}: la ficha de la empresa."""

from datetime import date
from uuid import UUID, uuid4

from app.modules.clients.models import CompanyRutVersion, CompanyUser
from app.modules.platform.models import SystemRole
from tests.integration.conftest import auth_headers
from tests.integration.test_companies_list import screen  # noqa: F401 (fixture)
from tests.integration.test_engagements import team  # noqa: F401 (fixture)

URL = "/api/v1/companies"


def detail(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_company_detail(client, admin, screen):  # noqa: F811
    data = detail(await client.get(f"{URL}/{screen.andina['company']['id']}", headers=admin))

    company = data["company"]
    assert (company["display_name"], company["nit"], company["dv"]) == (
        "Comercializadora Andina SAS",
        "900123456",
        "8",
    )
    assert company["trade_name"] == "Andina Comercial"
    assert company["notes"] == "Prefiere reuniones los martes."  # completas
    assert company["tax_responsibilities"] == ["05", "48", "42"]
    assert company["group"] is None
    assert (data["status"], data["rut_date_unknown"], data["group_companies"]) == (
        "activo",
        False,
        [],
    )

    [engagement] = data["engagements"]
    assert (
        engagement["obligation"]["name"],
        engagement["service_type"]["name"],
        engagement["fiscal_year"],
        engagement["status"],
        engagement["partner"]["full_name"],
        engagement["manager"]["full_name"],
    ) == ("Información exógena", "Elaboración", 2025, "por_iniciar", "Juan Restrepo", "María Gómez")

    [version] = data["rut_versions"]
    assert (version["covers_from_year"], version["covers_to_year"]) == (2026, None)
    assert version["uploaded_by"]["full_name"] == "Persona Prueba"  # el administrador
    assert data["users"] == []


async def test_group_shows_the_other_companies(client, admin, screen):  # noqa: F811
    data = detail(await client.get(f"{URL}/{screen.muisca['company']['id']}", headers=admin))

    assert data["company"]["group"]["name"] == "Grupo Muisca"
    assert [(c["display_name"], c["status"]) for c in data["group_companies"]] == [
        ("Andina Zona Franca SAS", "activo")
    ]


async def test_rut_versions_and_the_years_they_cover(client, admin, screen, db_session):  # noqa: F811
    company_id = UUID(screen.andina["company"]["id"])
    db_session.add_all(
        [
            CompanyRutVersion(
                company_id=company_id,
                generated_at=date(2024, 3, 10),
                rut_updated_at=date(2024, 3, 1),
                covers_tax_year=2024,
                is_historical=True,
            ),
            # Actualizada el 1 de enero: cubre desde el año anterior
            CompanyRutVersion(
                company_id=company_id,
                generated_at=date(2023, 1, 5),
                rut_updated_at=date(2023, 1, 1),
                covers_tax_year=2022,
                is_historical=True,
            ),
        ]
    )
    await db_session.commit()

    data = detail(await client.get(f"{URL}/{company_id}", headers=admin))

    assert [
        (v["rut_updated_at"], v["covers_from_year"], v["covers_to_year"], v["is_historical"])
        for v in data["rut_versions"]
    ] == [
        ("2026-09-12", 2026, None, False),  # la vigente, hasta hoy
        ("2024-03-01", 2024, 2025, True),
        ("2023-01-01", 2022, 2023, True),
    ]


async def test_partner_sees_only_companies_of_his_engagements(client, screen, team, firm):  # noqa: F811
    socio = auth_headers(team.socio, firm)
    assert (
        await client.get(f"{URL}/{screen.andina['company']['id']}", headers=socio)
    ).status_code == 200
    assert (
        await client.get(f"{URL}/{screen.muisca['company']['id']}", headers=socio)
    ).status_code == 404


async def test_client_user_sees_its_company_but_not_the_rest_of_the_group(
    client,
    screen,  # noqa: F811
    platform,
    firm,
    db_session,
):
    laura = await platform.user("laura@muisca.co", "Laura Pineda")
    await platform.member(laura, firm, SystemRole.CLIENTE)
    muisca_id = UUID(screen.muisca["company"]["id"])
    db_session.add(
        CompanyUser(company_id=muisca_id, email="laura@muisca.co", full_name="Laura", user_id=laura)
    )
    await db_session.commit()
    headers = auth_headers(laura, firm)

    data = detail(await client.get(f"{URL}/{muisca_id}", headers=headers))
    assert data["group_companies"] == []  # no ve la otra empresa del grupo
    assert [u["email"] for u in data["users"]] == ["laura@muisca.co"]
    other = screen.zona_franca["company"]["id"]
    assert (await client.get(f"{URL}/{other}", headers=headers)).status_code == 404


async def test_unknown_or_unauthorized(client, admin, screen, platform, firm):  # noqa: F811
    assert (await client.get(f"{URL}/{uuid4()}", headers=admin)).status_code == 404
    company = screen.andina["company"]["id"]
    assert (await client.get(f"{URL}/{company}")).status_code == 401
    outsider = auth_headers(await platform.user("externo@x.co"), firm)
    assert (await client.get(f"{URL}/{company}", headers=outsider)).status_code == 403
