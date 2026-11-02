from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_liveness(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_when_started(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_not_ready_when_a_dependency_fails(settings: Settings) -> None:
    async def db_down() -> bool:
        return False

    with TestClient(create_app(settings, checks={"db": db_down})) as c:
        r = c.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "not-ready", "checks": {"db": False}}
