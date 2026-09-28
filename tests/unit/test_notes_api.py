"""Tests del router con un service falso: no necesitan base de datos.
El mismo patrón sirve para cualquier módulo (reemplazar su get_<x>_service)."""

import uuid

import pytest

from app.core.exceptions import NotFoundError
from app.main import app
from app.modules.notes.dependencies import get_note_service
from app.modules.notes.models import Note
from app.shared.pagination import Page


class FakeNoteService:
    def __init__(self):
        self.notes: dict[uuid.UUID, Note] = {}

    async def list(self, params, actor):
        mine = [n for n in self.notes.values() if n.user_id == actor.id]
        return Page.create(mine, len(mine), params)

    async def get(self, item_id, actor):
        note = self.notes.get(item_id)
        if note is None or note.user_id != actor.id:
            raise NotFoundError("Note not found")
        return note

    async def create(self, data, actor):
        note = Note(**data.model_dump(), user_id=actor.id, created_by=actor.id)
        self.notes[note.id] = note
        return note


@pytest.fixture
def service():
    fake = FakeNoteService()
    app.dependency_overrides[get_note_service] = lambda: fake
    return fake


async def test_requires_authentication(client, service):
    response = await client.get("/api/v1/notes")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_create_takes_owner_from_token(client, service, authenticated):
    response = await client.post(
        "/api/v1/notes",
        json={"title": "Hello", "content": "World", "user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["user_id"] == str(authenticated.id)


async def test_list_is_paginated(client, service, authenticated):
    for i in range(3):
        await client.post("/api/v1/notes", json={"title": f"n{i}", "content": "x"})

    response = await client.get("/api/v1/notes", params={"page": 1, "size": 2})
    data = response.json()["data"]
    assert data["total"] == 3
    assert data["pages"] == 2
    assert len(data["items"]) == 3  # el service falso no corta la página


async def test_not_found_uses_error_envelope(client, service, authenticated):
    response = await client.get(f"/api/v1/notes/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize("params", [{"size": 500}, {"page": 0}, {"sort": "DROP TABLE"}])
async def test_invalid_pagination_is_rejected(client, service, authenticated, params):
    response = await client.get("/api/v1/notes", params=params)
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
