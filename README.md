# Bharat Trading Platform

India-first algorithmic trading platform under active implementation. **Not production ready.**
The existing foundation is being completed in verified slices; live execution is unavailable.
See [implementation status](docs/IMPLEMENTATION_STATUS.md) for implemented behavior and gaps.

## Local setup (Linux, macOS, or Windows WSL2)

Python 3.12+, uv, and Docker Compose are required for the PostgreSQL development stack.

```bash
uv sync --frozen --extra dev
python scripts/configure_local.py
# Generates random local credentials in an ignored .env; refuses to overwrite it.
docker compose up -d postgres redis
# Migrations use the owner account; application processes use mts_app.
set -a
. ./.env
set +a
MTS_DATABASE_URL="$MTS_MIGRATION_DATABASE_URL" uv run --frozen alembic -c infra/migrations/alembic.ini upgrade head
uv run --frozen uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Or start the whole backend stack, including migration job and worker:

```bash
docker compose up --build -d api worker
curl --fail http://localhost:8000/health/ready
docker compose --profile monitoring up -d prometheus
```

The API's OpenAPI documentation is at `http://localhost:8000/docs`.
Liveness: `/health/live`; schema/dependency readiness: `/health/ready`; metrics: `/metrics`.
Readiness describes service availability, **not permission to trade**.

## Worker and operator controls

```bash
uv run --frozen python -m apps.worker.main
uv run --frozen python -m apps.worker.main --once
uv run --frozen python -m apps.manage safety
uv run --frozen python -m apps.manage kill-switch on --reason 'Operator maintenance'
```

The worker persists dependency health and activates the kill switch on dependency failures
when the database is reachable. A database failure itself prevents durable order processing.
The switch starts on. A local operator can explicitly run `kill-switch off --reason '...'`;
this never authorizes or enables live execution. Changes and audit events commit together.

## Checks and builds

```bash
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy apps packages
uv run --frozen pytest -q
uv run --frozen bandit -q -r apps packages
uv run --frozen pip-audit --disable-pip --no-deps -r requirements.lock
uv build
docker compose build api worker
```

CI additionally applies, checks, rolls back, and reapplies migrations on a disposable PostgreSQL
instance; runs opt-in PostgreSQL recovery tests; builds/scans the container; and starts Compose
using a non-superuser application account. No CI job deploys or enables live trading.
Never downgrade a production database using these disposable-test instructions.

## Development without Docker

SQLite is supported for local tests and API/worker smoke checks only:

```bash
export MTS_DATABASE_URL=sqlite+aiosqlite:///./local.db
export MTS_REDIS_REQUIRED=false
uv run --frozen alembic -c infra/migrations/alembic.ini upgrade head
uv run --frozen python -m apps.worker.main --once
uv run --frozen uvicorn apps.api.main:app --host 127.0.0.1
```

SQLite checks do not establish PostgreSQL concurrency or production reliability.

## Trading, brokers, and frontend

Backtesting, paper execution, live brokers, ML, and the complete frontend are still tracked in
[the roadmap](docs/ROADMAP.md). No command claims those unavailable workflows are functional.
Upstox/Dhan variable names are documented in `.env.example`; there is no authenticated broker
connection and no broker call in the foundation. All configured live startup attempts fail.

Dependency lock updates: `uv lock`, followed by
`uv export --frozen --no-dev --no-emit-project -o requirements.lock`. Commit both locks together.
