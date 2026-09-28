import pytest

from tests.integration.conftest import auth_headers


@pytest.fixture
def person(platform):
    """Crea una persona en la plataforma y devuelve sus encabezados."""

    async def _person(email: str) -> dict[str, str]:
        return auth_headers(await platform.user(email))

    return _person


async def test_notes_crud_is_scoped_to_owner(client, person):
    alice = await person("alice@example.com")
    bob = await person("bob@example.com")

    created = await client.post(
        "/api/v1/notes", json={"title": "Plan", "content": "v1"}, headers=alice
    )
    assert created.status_code == 201
    note = created.json()["data"]
    url = f"/api/v1/notes/{note['id']}"

    # El dueño la ve
    listing = (await client.get("/api/v1/notes", headers=alice)).json()["data"]
    assert listing["total"] == 1

    # Otro usuario ni siquiera sabe que existe
    assert (await client.get("/api/v1/notes", headers=bob)).json()["data"]["total"] == 0
    assert (await client.get(url, headers=bob)).status_code == 404
    assert (await client.delete(url, headers=bob)).status_code == 404

    # Edición parcial
    updated = await client.patch(url, json={"content": "v2"}, headers=alice)
    assert updated.status_code == 200
    assert updated.json()["data"]["content"] == "v2"
    assert updated.json()["data"]["title"] == "Plan"
    assert updated.json()["data"]["updated_at"] is not None

    # Borrado lógico
    assert (await client.delete(url, headers=alice)).status_code == 200
    assert (await client.get(url, headers=alice)).status_code == 404


async def test_sorting(client, person):
    alice = await person("sorter@example.com")
    for title in ("b", "a", "c"):
        await client.post("/api/v1/notes", json={"title": title, "content": "x"}, headers=alice)

    response = await client.get("/api/v1/notes", params={"sort": "title"}, headers=alice)
    assert [n["title"] for n in response.json()["data"]["items"]] == ["a", "b", "c"]

    invalid = await client.get("/api/v1/notes", params={"sort": "content"}, headers=alice)
    assert invalid.status_code == 400
    assert invalid.json()["details"]["allowed"] == ["created_at", "title", "updated_at"]
