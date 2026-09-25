import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from pydantic import BaseModel, Field

from apps.api.replay import create_replay_router
from packages.auth import (
    AuthenticationError,
    AuthenticationUnavailable,
    AuthorizationError,
    PersistentTokenRevocationStore,
    Principal,
    Role,
    TokenAuthenticator,
)
from packages.config import Settings, get_settings
from packages.database import Database
from packages.observability.logging import configure_logging
from packages.replay import (
    ReplayCoordinator,
    ReplayDatasetRepository,
    ReplayScheduler,
    ReplayScheduleResult,
    ReplaySessionRepository,
    ReplayTaskManager,
    ReplayTaskRequest,
    ReplayTaskStatus,
    ReplayTaskStatusRepository,
)

REQUESTS = Counter("mts_http_requests_total", "HTTP requests", ("method", "path", "status"))
logger = logging.getLogger(__name__)
WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


class TokenRevocationRequest(BaseModel):
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=512)


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    config = settings or get_settings()
    db = database or Database(config.database_url)
    configure_logging(config.log_level)
    authenticator = TokenAuthenticator(
        viewer_token=(
            config.api_viewer_token.get_secret_value() if config.api_viewer_token else None
        ),
        operator_token=(
            config.api_operator_token.get_secret_value() if config.api_operator_token else None
        ),
        previous_viewer_token=(
            config.api_previous_viewer_token.get_secret_value()
            if config.api_previous_viewer_token
            else None
        ),
        previous_operator_token=(
            config.api_previous_operator_token.get_secret_value()
            if config.api_previous_operator_token
            else None
        ),
        previous_tokens_expire_at=config.api_previous_tokens_expire_at,
        revoked_token_sha256=tuple(config.api_revoked_token_sha256),
    )

    async def run_replay_task(
        request: ReplayTaskRequest, stop: asyncio.Event
    ) -> ReplayScheduleResult:
        async def interruptible_sleep(delay: float) -> None:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)

        async with db.sessions() as replay_session:
            scheduler = ReplayScheduler(
                ReplayCoordinator(
                    ReplaySessionRepository(replay_session),
                    ReplayDatasetRepository(replay_session),
                ),
                commit=replay_session.commit,
                sleep=interruptible_sleep,
            )
            return await scheduler.run(
                request.session_id,
                expected_version=request.expected_version,
                candles_per_second=request.candles_per_second,
                maximum_steps=request.maximum_steps,
                should_stop=stop.is_set,
            )

    async def persist_replay_task(status: ReplayTaskStatus) -> None:
        async with db.sessions() as replay_session:
            await ReplayTaskStatusRepository(replay_session).record(status)
            await replay_session.commit()

    replay_tasks = ReplayTaskManager(run_replay_task, status_observer=persist_replay_task)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "service_started mode=%s live_enabled=%s",
            config.trading_mode,
            config.live_trading_enabled,
        )
        try:
            yield
        finally:
            await replay_tasks.close()
            await db.close()

    app = FastAPI(title="Bharat Trading Platform API", version="0.1.0", lifespan=lifespan)
    app.state.database = db
    app.state.settings = config
    app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="web-assets")
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
        request.state.correlation_id = correlation_id
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

    @app.get("/replay", include_in_schema=False)
    async def replay_console() -> FileResponse:
        return FileResponse(
            WEB_ROOT / "replay.html",
            headers={
                "Content-Security-Policy": (
                    "default-src 'self'; connect-src 'self'; img-src 'self'; "
                    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
                ),
                "Cache-Control": "no-store",
            },
        )

    async def authenticated_principal(
        authorization: str | None = Header(default=None),
    ) -> Principal:
        try:
            principal = authenticator.authenticate(authorization)
        except AuthenticationUnavailable as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
        except AuthenticationError as error:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                str(error),
                headers={"WWW-Authenticate": "Bearer"},
            ) from error
        if config.api_persistent_revocation_enabled:
            try:
                async with db.sessions() as session:
                    revoked = await PersistentTokenRevocationStore(session).is_revoked(
                        principal.credential_sha256,
                        as_of=datetime.now(UTC),
                    )
            except Exception as error:
                logger.error("persistent_auth_revocation_check_failed")
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "persistent revocation check is unavailable",
                ) from error
            if revoked:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    "bearer authorization is invalid",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return principal

    def operator_principal(
        principal: Annotated[Principal, Depends(authenticated_principal)],
    ) -> Principal:
        try:
            return authenticator.require(principal, Role.OPERATOR)
        except AuthorizationError as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error

    @app.get("/api/v1/session", tags=["access"])
    async def session(
        principal: Annotated[Principal, Depends(authenticated_principal)],
    ) -> dict[str, str]:
        return {
            "subject": principal.subject,
            "role": principal.role.value,
            "trading_mode": config.trading_mode.value,
        }

    @app.get("/api/v1/operator/mode", tags=["access"])
    async def operator_mode(
        principal: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, str]:
        return {
            "subject": principal.subject,
            "role": principal.role.value,
            "trading_mode": config.trading_mode.value,
        }

    @app.post(
        "/api/v1/operator/token-revocations",
        tags=["access"],
        status_code=status.HTTP_201_CREATED,
    )
    async def revoke_api_token(
        payload: TokenRevocationRequest,
        request: Request,
        principal: Annotated[Principal, Depends(operator_principal)],
    ) -> dict[str, str]:
        if not config.api_persistent_revocation_enabled:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "persistent revocation is not enabled",
            )
        try:
            async with db.sessions() as session:
                record = await PersistentTokenRevocationStore(session).revoke(
                    token_sha256=payload.token_sha256,
                    revoked_at=datetime.now(UTC),
                    actor_id=principal.subject,
                    reason=payload.reason,
                    correlation_id=request.state.correlation_id,
                )
                await session.commit()
        except ValueError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except Exception as error:
            logger.error("persistent_auth_revocation_write_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "persistent revocation write is unavailable",
            ) from error
        return {
            "id": str(record.id),
            "token_sha256": record.token_sha256,
            "revoked_at": record.revoked_at.isoformat(),
        }

    app.include_router(
        create_replay_router(
            db,
            task_manager=replay_tasks,
            authenticated_principal=authenticated_principal,
            operator_principal=operator_principal,
        )
    )

    return app


app = create_app()
