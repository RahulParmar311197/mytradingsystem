import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from packages.config import Settings, get_settings
from packages.database import Database
from packages.observability.logging import configure_logging

REQUESTS = Counter("mts_http_requests_total", "HTTP requests", ("method", "path", "status"))
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    config = settings or get_settings()
    db = database or Database(config.database_url)
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "service_started mode=%s live_enabled=%s",
            config.trading_mode,
            config.live_trading_enabled,
        )
        yield
        await db.close()

    app = FastAPI(title="Bharat Trading Platform API", version="0.1.0", lifespan=lifespan)
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
    async def correlation_and_security(request: Request, call_next: object) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))[:64]
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        REQUESTS.labels(request.method, request.url.path, response.status_code).inc()
        return response

    @app.get("/health/live", tags=["system"])
    async def liveness() -> dict[str, str]:
        return {"status": "alive", "trading_mode": config.trading_mode.value}

    @app.get("/health/ready", tags=["system"])
    async def readiness(response: Response) -> dict[str, object]:
        database_ready = await db.is_ready()
        if not database_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ready" if database_ready else "not_ready",
            "checks": {"database": database_ready},
            "trading_mode": config.trading_mode.value,
        }

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
