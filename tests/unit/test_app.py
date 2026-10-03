"""Comportamiento transversal: formato de respuestas, manejo de errores, request id, CORS."""

from fastapi import APIRouter
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError
from app.main import app

router = APIRouter()


@router.get("/_test/conflict")
def raise_conflict():
    raise ConflictError("Already there", details={"field": "email"})


@router.get("/_test/integrity")
def raise_integrity():
    raise IntegrityError("INSERT ...", {}, Exception("duplicate key value"))


@router.get("/_test/boom")
def raise_unhandled():
    raise RuntimeError("secret internal detail")


app.include_router(router)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_error_is_translated(client):
    response = client.get("/_test/conflict")
    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "message": "Already there",
        "code": "conflict",
        "details": {"field": "email"},
    }


def test_integrity_error_is_409(client):
    response = client.get("/_test/integrity")
    assert response.status_code == 409
    assert response.json()["code"] == "integrity_error"


def test_unhandled_error_does_not_leak_details(client):
    response = client.get("/_test/boom")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "secret" not in response.text


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["ok"] is False


def test_request_id_is_generated_and_propagated(client):
    assert len((client.get("/health")).headers["x-request-id"]) == 32
    response = client.get("/health", headers={"X-Request-ID": "from-bff-123"})
    assert response.headers["x-request-id"] == "from-bff-123"


def test_cors_only_allows_configured_origins(client):
    preflight = {"Access-Control-Request-Method": "GET"}
    allowed = client.options(
        "/api/v1/obligations", headers={"Origin": "http://localhost:3000", **preflight}
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"

    denied = client.options(
        "/api/v1/obligations", headers={"Origin": "https://evil.example", **preflight}
    )
    assert "access-control-allow-origin" not in denied.headers
