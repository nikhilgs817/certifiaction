from __future__ import annotations

from fastapi.testclient import TestClient


def test_info(client: TestClient) -> None:
    r = client.get("/api/v1/info")
    assert r.status_code == 200
    assert r.json() == {"service": "test-svc", "version": "abc123", "environment": "test"}
    assert r.headers["x-request-id"]


def test_echo_validates_input(client: TestClient) -> None:
    assert client.post("/api/v1/echo", json={"message": ""}).status_code == 422
    r = client.post("/api/v1/echo", json={"message": "hi"})
    assert r.status_code == 200
    assert r.json()["length"] == 2
