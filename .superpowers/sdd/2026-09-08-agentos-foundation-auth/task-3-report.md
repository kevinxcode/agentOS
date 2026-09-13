# Task 3 Report: Private Docker Compose Infrastructure

## Status

DONE WITH ENVIRONMENT BLOCKER

The requested production and development Compose infrastructure is implemented and all available static and repository checks pass. Docker Compose model validation, image builds, and the runtime smoke test could not run because this execution environment has no `docker` executable.

## Summary

- Added a production Compose topology for `web`, `api`, PostgreSQL with pgvector, Redis, and MinIO on the internal `agentos_private` network.
- Published only the web service's port in production; API and data services use internal `expose` entries only. The development override publishes private-service ports on `127.0.0.1` only.
- Required all API URLs and secrets via `AGENTOS_*` interpolation without embedding production credentials in YAML.
- Added health checks, restart policies, read-only root filesystems, temporary writable mounts, dropped capabilities, `no-new-privileges`, and named PostgreSQL/MinIO volumes.
- Added a private, one-shot MinIO client service to create the required bucket before API readiness starts.
- Added locked, non-root production images for the FastAPI factory and pinned pnpm/Corepack Next.js build.
- Added a bounded smoke script that validates Compose configuration, waits up to 120 seconds for the five long-lived services, checks API liveness from the web container, prints service state on failure, and always tears down containers while retaining volumes unless `PURGE=1`.

## Files Changed

- `.dockerignore`
- `compose.yaml`
- `infra/compose/compose.dev.yaml`
- `infra/compose/postgres/init.sql`
- `services/api/Dockerfile`
- `apps/web/Dockerfile`
- `scripts/compose_smoke.sh`
- `tests/contracts/test_compose_security.py`

## Commands and Exact Results

- `pytest tests/contracts/test_compose_security.py -q` before implementation — exited 127 because the bare `pytest` executable is not on `PATH`; this was an environment error and was not counted as the RED result.
- `uv run --project services/api pytest tests/contracts/test_compose_security.py -q` before implementation — failed as intended: `2 failed in 0.08s`, both with `FileNotFoundError: compose.yaml`.
- `uv run --project services/api pytest tests/contracts/test_compose_security.py -q` after implementation — `2 passed in 0.03s`.
- Static Python validation of the parsed production/development YAML — exited 0 with `static Compose invariants: PASS`; verified required services, only-web port publication, internal network, named volumes, health checks, private `expose` entries, capability/security settings, required API interpolation, and loopback-only development bindings.
- Strict `Settings` construction using the smoke environment — exited 0 with `smoke environment Settings validation: PASS`.
- `bash -n scripts/compose_smoke.sh` — exited 0.
- `uv run --project services/api pytest tests/contracts/test_repository_layout.py::test_environment_template_has_only_empty_required_values -q` after reverting an out-of-scope environment-template addition — `1 passed in 0.01s`.
- Final `uv run --project services/api pytest tests/contracts/test_compose_security.py -q && bash -n scripts/compose_smoke.sh && make lint && make typecheck && make test && make build && git diff --cached --check` — exited 0: security contract `2 passed in 0.03s`; ESLint and Ruff passed; TypeScript and mypy passed; Vitest `1 passed`; pytest `30 passed in 0.56s`; Next.js 16.3.4 production build compiled, type-checked, and generated all static pages; no cached-diff whitespace errors.
- `docker --version; docker compose version; docker info --format '{{.ServerVersion}}'` — exited 127; every command reported `/bin/bash: docker: command not found`.
- `bash scripts/compose_smoke.sh` — exited 127 at `docker compose config --quiet` with `scripts/compose_smoke.sh: line 40: docker: command not found`; the failure trap also attempted `docker compose ps` and teardown, which reported the same missing executable at lines 27 and 33.
- `docker compose config --quiet` and daemon-backed image build/start/health validation — not executable because the Docker CLI is absent.

## Commit

Implementation commit: `4202a22d85dd4a4d36fe768e2a734bf586a085de`.

## Self-Review

- The production model has exactly one port-publishing service (`web`); API, PostgreSQL, Redis, MinIO, and the MinIO initializer have no `ports` key.
- Every service joins only the internal `agentos_private` network; none is privileged or mounts the Docker socket.
- All long-lived services define health checks and restart policies. Read-only filesystems have explicit writable paths, and all services drop Linux capabilities; PostgreSQL adds back only the entrypoint capabilities needed to initialize its named data volume.
- The API starts the inspected `agentos.api.app:create_app` callable with Uvicorn's `--factory` flag and checks `/health/ready` using Python's standard library.
- The MinIO bucket is created before API startup so the existing `head_bucket` readiness check can succeed without changing accepted API behavior.
- Production YAML contains only required environment substitutions for credentials. Smoke-only deterministic values live in the test script and satisfy the strict settings lengths and URL schemes.
- The smoke script's `EXIT` trap preserves named volumes by default and removes them only when `PURGE=1`; a failed local run demonstrated that the failure path attempts both state printing and teardown.

## Concerns

- Docker Compose schema rendering, image availability/builds, container capability compatibility, and the five-service health/liveness smoke remain unverified in this environment because the Docker CLI is absent. Run `bash scripts/compose_smoke.sh` on a Docker-enabled host before promotion.
