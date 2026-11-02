"""FastAPI app factory: health, readiness, metrics, JSON access logs and a tiny typed API."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.logging_setup import configure_logging
from app.metrics import LATENCY, REQUESTS, UNOBSERVED, metrics_response, route_of
from app.schemas import EchoIn, EchoOut, Health, Info, Ready

log = logging.getLogger("app")
ReadinessCheck = Callable[[], Awaitable[bool]]


def create_app(settings: Settings | None = None, checks: dict[str, ReadinessCheck] | None = None) -> FastAPI:
    """`checks` are async callables (database, cache, ...) that must all pass for /readyz to return 200."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level, cfg.service_name)
    readiness = checks or {}
    state = {"started": False}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["started"] = True
        log.info("startup version=%s environment=%s", cfg.version, cfg.environment)
        yield
        state["started"] = False
        log.info("shutdown")

    app = FastAPI(title=cfg.service_name, version=cfg.version, lifespan=lifespan)

    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response = await call_next(request)
        route = route_of(request)
        if route not in UNOBSERVED:
            elapsed = time.perf_counter() - start
            REQUESTS.labels(request.method, route, str(response.status_code)).inc()
            LATENCY.labels(request.method, route).observe(elapsed)
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": route,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 1),
                    "request_id": request_id,
                },
            )
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/healthz", response_model=Health)
    async def healthz() -> Health:
        """Liveness: the process answers. Never checks dependencies (a DB outage must not restart pods)."""
        return Health()

    @app.get("/readyz", response_model=Ready)
    async def readyz() -> JSONResponse:
        """Readiness: started and every dependency check passes; otherwise 503 and the Service stops routing here."""
        results = {name: await check() for name, check in readiness.items()}
        ok = state["started"] and all(results.values())
        body = Ready(status="ready" if ok else "not-ready", checks=results)
        return JSONResponse(body.model_dump(), status_code=200 if ok else 503)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return metrics_response()

    @app.get("/api/v1/info", response_model=Info)
    async def info() -> Info:
        return Info(service=cfg.service_name, version=cfg.version, environment=cfg.environment)

    @app.post("/api/v1/echo", response_model=EchoOut)
    async def echo(body: EchoIn) -> EchoOut:
        return EchoOut(message=f"{cfg.greeting}: {body.message}", length=len(body.message), service=cfg.service_name)

    return app


app = create_app()
