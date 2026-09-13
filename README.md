# AgentOS — foundation and authentication

Local-first mission control for one administrator. This milestone implements
the hardened Compose foundation, password + mandatory TOTP authentication,
one-time recovery codes, protected Mission Control shell, and read-only audit log.
Tasks, workers, Kanban, model providers, and GitHub delivery are **not implemented**.

## Start here

- [Ubuntu installation and upgrades](docs/operations/ubuntu-deployment.md)
- [Cloudflare HTTPS entry point](docs/operations/cloudflare-tunnel.md)
- [Encrypted backup and disposable restore rehearsal](docs/operations/backup-restore.md)
- [Approved MVP design](docs/superpowers/specs/2026-09-08-agentos-mvp-design.md)
- [Foundation implementation plan](docs/superpowers/plans/2026-09-08-agentos-foundation-auth.md)

## Development checks

Use Python 3.13.5, Node 22.16.0, Corepack 0.34.6, pnpm 10.15.1, uv 0.12.8,
and Docker Engine with Compose v2. Install pinned tooling through your approved
package channel. Do not change the lockfiles merely to get an install through.

```bash
export COREPACK_HOME="$PWD/.corepack"
corepack pnpm@10.15.1 install --frozen-lockfile
uv sync --frozen --project services/api --extra dev
uv pip install --python services/api/.venv/bin/python PyYAML==6.0.2
services/api/.venv/bin/ruff check services/api tests scripts
services/api/.venv/bin/mypy services/api/src
services/api/.venv/bin/pytest -q
corepack pnpm@10.15.1 lint
corepack pnpm@10.15.1 typecheck
corepack pnpm@10.15.1 test
corepack pnpm@10.15.1 build
for script in scripts/*.sh; do bash -n "$script"; done
shellcheck -x scripts/*.sh
```

`pytest` runs real migrated SQLite/HTTP acceptance locally. With an explicit
`AGENTOS_TEST_DATABASE_URL` pointing to a **fresh disposable `agentos_test`**
PostgreSQL database, the focused foundation test runs against PostgreSQL and
also verifies its singleton constraint and timezone behavior. It never drops
tables or resets an existing database.

The six Playwright UI tests use a controlled fake auth service; they do not
prove the production backend. The separate real-stack gate does:

```bash
corepack pnpm@10.15.1 --filter @agentos/web exec playwright install --with-deps chromium
corepack pnpm@10.15.1 --filter @agentos/web test:e2e
bash scripts/compose_smoke.sh
AGENTOS_COMPOSE_ACCEPTANCE=1 services/api/.venv/bin/pytest tests/acceptance/test_foundation_acceptance.py -q
```

Both smoke scripts create uniquely named disposable projects and stop their
containers at exit. They retain named volumes for inspection and print exact
names; deletion is an explicit operator action. Never set production credentials
in a CI environment. No screenshots/traces/recovery-code artifacts are uploaded.

CI uses read-only permissions and SHA-pinned actions, with independent backend,
frontend, Compose, dependency-audit, image-scan and acceptance jobs. Scanners fail
closed; findings need a reviewed dependency upgrade, not an unreviewed suppression.
Production Compose commands in the runbook use `scripts/agentos-compose.sh`, which
prevents inherited `AGENTOS_*` values from shadowing the selected protected env file.

## Promotion status

Passing local SQLite/unit checks is not the Plan 1 completion gate. Docker image
execution, real PostgreSQL, Chromium, TLS/Tunnel, scanner results and a successful
encrypted restore rehearsal must be evidenced on CI/an Ubuntu host before
production promotion or Plan 2. See the task report for actual executor results.
