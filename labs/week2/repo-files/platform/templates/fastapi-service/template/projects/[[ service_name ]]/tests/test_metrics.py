from __future__ import annotations

from fastapi.testclient import TestClient


def test_metrics_use_route_templates(client: TestClient) -> None:
    client.get("/api/v1/info")
    body = client.get("/metrics").text
    assert 'http_requests_total{method="GET",route="/api/v1/info",status="200"}' in body
    assert 'route="/healthz"' not in body  # probes are not counted
