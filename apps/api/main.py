import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import RequestResponseEndpoint

from packages.config import Settings, get_settings
from packages.config.settings import TradingMode
from packages.database import Database
from packages.observability.dependencies import dependency_checks
from packages.observability.logging import configure_logging, correlation_context
from packages.observability.tracing import configure_tracing, tracer_for

REQUESTS = Counter("mts_http_requests_total", "HTTP requests", ("method", "path", "status"))
LATENCY = Histogram("mts_http_request_seconds", "Request duration", ("method", "path"))
DEPENDENCIES = Gauge("mts_dependency_ready", "Dependency readiness", ("dependency",))
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    config = settings or get_settings()
    if config.trading_mode is TradingMode.LIVE:
        raise RuntimeError(
            "live execution is unavailable in this release; configuration is not authorization"
        )
    db = database or Database(config.database_url)
    configure_logging(config.log_level)
    provider = configure_tracing(config.otel_endpoint)
    tracer = tracer_for(provider)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "service_started",
            extra={"trading_mode": config.trading_mode.value, "live_execution_available": False},
        )
        try:
            yield
        finally:
            await db.close()
            provider.shutdown()

    app = FastAPI(title="Bharat Trading Platform API", version="0.2.0", lifespan=lifespan)
    app.state.database = db
    app.state.settings = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
    )

    @app.middleware("http")
    async def correlation_and_security(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        supplied = request.headers.get("X-Correlation-ID", "")
        correlation_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else str(uuid4())
        )
        request.state.correlation_id = correlation_id
        token = correlation_context.set(correlation_id)
        start = perf_counter()
        try:
            with tracer.start_as_current_span("http.request") as span:
                span.set_attribute("http.request.method", request.method)
                try:
                    response = await call_next(request)
                except Exception:
                    logger.exception("request_failed")
                    response = JSONResponse(
                        status_code=500,
                        content={
                            "error": {"code": "INTERNAL_ERROR", "correlation_id": correlation_id}
                        },
                    )
                route = getattr(request.scope.get("route"), "path", "unmatched")
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", response.status_code)
            response.headers.update(
                {
                    "X-Correlation-ID": correlation_id,
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "Cache-Control": "no-store",
                }
            )
            if config.environment == "production":
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
            REQUESTS.labels(request.method, route, response.status_code).inc()
            LATENCY.labels(request.method, route).observe(perf_counter() - start)
            return response
        finally:
            correlation_context.reset(token)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Omit input values and validator context from externally visible errors.
        errors = [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "details": errors,
                    "correlation_id": request.state.correlation_id,
                }
            },
        )

    @app.get("/health/live", tags=["system"])
    async def liveness() -> dict[str, str]:
        return {"status": "alive", "trading_mode": config.trading_mode.value}

    @app.get("/health/ready", tags=["system"])
    async def readiness(response: Response) -> dict[str, object]:
        checks = await dependency_checks(db, config)
        for name, ready in checks.items():
            DEPENDENCIES.labels(name).set(int(ready))
        ready = all(checks.values())
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ready" if ready else "not_ready",
            "checks": checks,
            "trading_mode": config.trading_mode.value,
            "live_execution_available": False,
        }

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
