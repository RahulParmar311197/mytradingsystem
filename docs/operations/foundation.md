# Foundation operations

Use the commands in README. A fresh database starts with entries locked. Migrations are a
separate job, never an API-startup side effect. Repeated migrations preserve existing safety state.
The operational worker records one current heartbeat per worker service; this release supports
one worker process. It is a dependency monitor, not a trading or distributed job worker yet.

Readiness checks the expected Alembic revision and presence of safety/audit tables; Redis PING is
required in Compose and production configuration. Dependency checks have short timeouts. Metrics
are low-cardinality; HTTP spans include method, route template, and status, never query/body data.
Set MTS_OTEL_ENDPOINT to an OTLP HTTP trace collector endpoint to export spans. No exporter is
contacted if unset. Prometheus alert rules are supplied; alert routing and Grafana remain pending.

Clean SQLite migration, worker process, and Uvicorn smoke checks are local evidence only.
CI supplies actual PostgreSQL and Redis services and builds/runs the deployment image.

Backup and restore must use PostgreSQL pg_dump/pg_restore with protected credentials and encrypted
storage. No production backup procedure is certified until a real restore drill has passed.
