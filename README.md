# Bharat Trading Platform

A safety-first modular monolith for an India-first algorithmic trading workflow. The repository currently
contains the audited Phase 1 foundation, historical-data slice, and causal technical-indicator engine; later
trading capabilities are explicitly tracked as incomplete.
Live trading is disabled by default and startup fails closed if any required live interlock is absent.

## Local setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
docker compose up -d postgres redis
alembic -c infra/migrations/alembic.ini upgrade head
uvicorn apps.api.main:app --reload
```

API documentation is at `http://localhost:8000/docs`; liveness, readiness and Prometheus metrics are
at `/health/live`, `/health/ready`, and `/metrics`.

## Worker, frontend, paper trading, and broker sandbox

The authenticated replay console is served at `/replay`; it exposes only persisted replay prefixes and guarded
operator controls. A general application frontend, worker runtime, and broker sandbox are not complete. Follow
[the roadmap](docs/ROADMAP.md) before enabling broader workflows.

## Quality and production build

```bash
ruff format --check . && ruff check .
mypy apps packages
pytest
bandit -q -r apps packages
alembic -c infra/migrations/alembic.ini upgrade head --sql >/tmp/migration.sql
docker compose build api
```

Never put broker credentials in `.env.example` or Git. The local Compose password is development-only.
