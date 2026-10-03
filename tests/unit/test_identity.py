"""Cómo se le habla a Identidad (sin red: se reemplaza httpx.put)."""

from uuid import uuid4

import httpx
import pytest

from app.core import identity as identity_module
from app.core.identity import IdentityClient, IdentityRejected, IdentityUnavailable

ORG, ENGAGEMENT, COMPANY, PERSON = uuid4(), uuid4(), uuid4(), uuid4()


@pytest.fixture
def calls(monkeypatch):
    """Reemplaza httpx.put; cada prueba fija la respuesta en calls["answer"]."""
    calls: dict = {"answer": httpx.Response(204)}

    def fake_put(url, *, json, headers, timeout):
        calls.update(url=url, json=json, headers=headers)
        answer = calls["answer"]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(identity_module.settings, "identidad_url", "http://identidad:8002/")
    monkeypatch.setattr(identity_module.httpx, "put", fake_put)
    return calls


def register(calls):
    IdentityClient("el-token", ORG).set_engagement_team(ENGAGEMENT, COMPANY, PERSON, ["socio"])


def test_sends_the_team_with_the_callers_token(calls):
    register(calls)

    assert calls["url"] == f"http://identidad:8002/compromisos/{ENGAGEMENT}/equipo/{PERSON}"
    assert calls["json"] == {"empresa_id": str(COMPANY), "roles": ["socio"]}
    assert calls["headers"]["Authorization"] == "Bearer el-token"
    assert calls["headers"]["X-Organization-Id"] == str(ORG)
    assert "X-Request-ID" in calls["headers"]


def test_rejection_keeps_identity_status_and_detail(calls):
    calls["answer"] = httpx.Response(404, json={"detail": "no es miembro"})
    with pytest.raises(IdentityRejected) as exc:
        register(calls)
    assert (exc.value.status, exc.value.detail) == (404, "no es miembro")


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(500), httpx.Response(503), httpx.ConnectError("sin red")],
    ids=["500", "503", "sin-red"],
)
def test_identity_down(calls, answer):
    calls["answer"] = answer
    with pytest.raises(IdentityUnavailable):
        register(calls)
