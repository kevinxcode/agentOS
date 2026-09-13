# AgentOS Foundation and Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a deployable AgentOS foundation with a Next.js dashboard, FastAPI control plane, private Docker Compose infrastructure, one local administrator, mandatory TOTP 2FA, recovery codes, session security, and audit events.

**Architecture:** A pnpm monorepo contains the web app while a Python package contains the API. PostgreSQL is the durable source of truth; Redis and MinIO are wired and health-checked for later milestones. The browser authenticates through opaque server-side sessions stored as hashes in PostgreSQL and transported only by secure cookies.

**Tech Stack:** Node.js 22, pnpm 10, Next.js 16, TypeScript 5, Tailwind CSS 4, shadcn/ui, Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2 async, Alembic, PostgreSQL 17, pgvector, Redis 7, MinIO, Argon2id, PyOTP, pytest, Vitest, Playwright, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-08-agentos-mvp-design.md`

## Global Constraints

- Deployment target is an always-on Ubuntu server using Docker Compose.
- The MVP has exactly one local administrator.
- Password hashing uses Argon2id and TOTP 2FA is mandatory after enrollment.
- Session cookies are `HttpOnly`, `Secure`, and `SameSite` protected.
- Recovery codes are one-time, hashed at rest, and shown only during enrollment.
- PostgreSQL is the durable source of truth; Redis stores transient state only.
- PostgreSQL, Redis, MinIO, API internals, and future model/runtime services must not publish public host ports in production.
- Durable credentials are encrypted at rest; master keys and application secrets never enter Git.
- Audit records never contain passwords, TOTP secrets, recovery codes, session tokens, or provider credentials.
- All implementation follows test-driven development and each task ends in a focused commit.

## Delivery Sequence

This is Plan 1 of 4:

1. Foundation and authentication (this plan).
2. Universal tasks, Kanban, durable runs, workers, approvals, and live events.
3. LiteLLM providers, model policy, usage, budget controls, and Ollama topology.
4. GitHub App, sandbox, OpenHands adapter, coding pipeline, review, and PR delivery.

Each plan must leave `main` runnable and independently testable.

## File Map

```text
agentOS/
├── apps/web/                         # Next.js browser application only
│   ├── app/(auth)/login/page.tsx
│   ├── app/(auth)/enroll/page.tsx
│   ├── app/(dashboard)/layout.tsx
│   ├── app/(dashboard)/page.tsx
│   ├── app/api/auth/[...path]/route.ts
│   ├── components/auth/login-form.tsx
│   ├── components/auth/totp-form.tsx
│   ├── lib/api/client.ts
│   └── lib/auth/session.ts
├── services/api/                     # FastAPI control plane only
│   ├── alembic/
│   ├── src/agentos/
│   │   ├── api/app.py
│   │   ├── api/routes/auth.py
│   │   ├── api/routes/health.py
│   │   ├── audit/models.py
│   │   ├── audit/service.py
│   │   ├── auth/models.py
│   │   ├── auth/schemas.py
│   │   ├── auth/service.py
│   │   ├── auth/totp.py
│   │   ├── config.py
│   │   ├── crypto.py
│   │   └── db.py
│   └── tests/
├── infra/compose/                    # Production and development composition
├── scripts/                          # Deterministic bootstrap and smoke checks
├── .github/workflows/ci.yml
├── compose.yaml
├── Makefile
├── package.json
├── pnpm-workspace.yaml
└── README.md
```

---

### Task 1: Monorepo Contract and Reproducible Tooling

**Files:**
- Create: `.editorconfig`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `Makefile`
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `services/api/pyproject.toml`
- Create: `services/api/src/agentos/__init__.py`
- Create: `tests/contracts/test_repository_layout.py`

**Interfaces:**
- Consumes: no application interface.
- Produces: `make install`, `make lint`, `make typecheck`, `make test`, `make build`, and the Python package `agentos`.

- [ ] **Step 1: Write the failing repository-layout contract**

```python
# tests/contracts/test_repository_layout.py
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_required_workspace_files_exist() -> None:
    required = [
        "package.json",
        "pnpm-workspace.yaml",
        "apps/web/package.json",
        "services/api/pyproject.toml",
        ".env.example",
    ]
    assert [name for name in required if not (ROOT / name).is_file()] == []


def test_secrets_are_not_present_in_env_example() -> None:
    text = (ROOT / ".env.example").read_text()
    assert "change-me" not in text
    assert "sk-" not in text
```

- [ ] **Step 2: Run the contract and verify failure**

Run: `python -m pytest tests/contracts/test_repository_layout.py -q`

Expected: FAIL because workspace files do not exist.

- [ ] **Step 3: Create pinned workspace manifests and safe examples**

Use this root script contract:

```json
{
  "private": true,
  "packageManager": "pnpm@10.15.1",
  "scripts": {
    "lint": "corepack pnpm@10.15.1 --filter @agentos/web lint",
    "typecheck": "corepack pnpm@10.15.1 --filter @agentos/web typecheck",
    "test": "corepack pnpm@10.15.1 --filter @agentos/web test",
    "build": "corepack pnpm@10.15.1 --filter @agentos/web build"
  }
}
```

Use `packages: ["apps/*"]` in `pnpm-workspace.yaml`. Define Python dependencies for FastAPI, uvicorn, pydantic-settings, SQLAlchemy async, asyncpg, Alembic, argon2-cffi, pyotp, cryptography, redis, boto3, structlog, and development dependencies pytest, pytest-asyncio, httpx, ruff, mypy. Pin direct dependencies and the build backend exactly; configure Ruff and mypy in `pyproject.toml`; commit both `services/api/uv.lock` and its exported `services/api/requirements.lock`.

`.env.example` must contain empty values for `AGENTOS_DATABASE_URL`, `AGENTOS_REDIS_URL`, `AGENTOS_MINIO_*`, `AGENTOS_SESSION_PEPPER`, and `AGENTOS_MASTER_KEY`; it must not contain usable secrets.

Use direct pinned Corepack commands only. Do not run `corepack enable` or rely on a globally shimmed `pnpm`; `Makefile` stores Corepack's cache in the ignored project-local `.corepack/` directory.

- [ ] **Step 4: Install dependencies and run the contract**

Run: `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 install --frozen-lockfile && uv sync --frozen --project services/api --extra dev && uv run --project services/api pytest tests/contracts/test_repository_layout.py -q`

Expected: PASS, 6 tests.

- [ ] **Step 5: Run formatting and type checks**

Run: `make lint && make typecheck && make test && make build`

Expected: all commands exit 0; this runs the pinned Corepack pnpm 10.15.1 web checks and frozen uv Python checks without global tool shims.

- [ ] **Step 6: Commit**

```bash
git add .editorconfig .env.example .gitignore Makefile package.json pnpm-workspace.yaml apps/web services/api tests
git commit -m "build: establish AgentOS workspace"
```

---

### Task 2: Configuration, Database, and Health API

**Files:**
- Create: `services/api/src/agentos/config.py`
- Create: `services/api/src/agentos/db.py`
- Create: `services/api/src/agentos/api/app.py`
- Create: `services/api/src/agentos/api/routes/health.py`
- Create: `services/api/tests/test_config.py`
- Create: `services/api/tests/api/test_health.py`

**Interfaces:**
- Consumes: environment names from Task 1.
- Produces: `Settings`, `get_settings()`, `session_factory`, `create_app()`, `GET /health/live`, and `GET /health/ready`.

- [ ] **Step 1: Write failing configuration tests**

```python
# services/api/tests/test_config.py
import pytest
from pydantic import ValidationError
from agentos.config import Settings


def test_production_rejects_insecure_cookie() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://u:p@db/app",
            redis_url="redis://redis:6379/0",
            session_pepper="x" * 32,
            master_key="eEl6dEdaSVdsYXVSaFRoVEQ4eW9ONW41SGRrWmh4MVk0dGVXTT0=",
            cookie_secure=False,
        )
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest services/api/tests/test_config.py -q`

Expected: FAIL because `Settings` does not exist.

- [ ] **Step 3: Implement strict settings and database lifecycle**

Implement `Settings(BaseSettings)` with the `AGENTOS_` prefix, required URLs and secrets, `environment: Literal["development", "test", "production"]`, and a model validator that rejects `cookie_secure=False` in production. Implement an async SQLAlchemy engine and `async_sessionmaker` without opening connections at import time.

- [ ] **Step 4: Write failing health tests**

```python
async def test_liveness_does_not_require_dependencies(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_readiness_reports_dependency_failure(client, broken_checks):
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unready"
```

- [ ] **Step 5: Implement the app factory and health endpoints**

`/health/live` returns process liveness. `/health/ready` concurrently checks PostgreSQL, Redis, and MinIO and returns only dependency names and states—never URLs or credentials. Add a request ID and structured access log middleware.

- [ ] **Step 6: Run focused and static tests**

Run: `pytest services/api/tests/test_config.py services/api/tests/api/test_health.py -q && ruff check services/api && mypy services/api/src`

Expected: all tests pass and both static checks exit 0.

- [ ] **Step 7: Commit**

```bash
git add services/api
git commit -m "feat(api): add configuration and health checks"
```

---

### Task 3: Private Docker Compose Infrastructure

**Files:**
- Create: `compose.yaml`
- Create: `infra/compose/compose.dev.yaml`
- Create: `infra/compose/postgres/init.sql`
- Create: `services/api/Dockerfile`
- Create: `apps/web/Dockerfile`
- Create: `scripts/compose_smoke.sh`
- Create: `tests/contracts/test_compose_security.py`

**Interfaces:**
- Consumes: `GET /health/ready` and environment contract.
- Produces: Compose services `web`, `api`, `postgres`, `redis`, and `minio`; internal network `agentos_private`; volumes `postgres_data` and `minio_data`.

- [ ] **Step 1: Write the failing Compose security contract**

```python
import yaml
from pathlib import Path


def test_only_web_publishes_a_production_port() -> None:
    model = yaml.safe_load(Path("compose.yaml").read_text())
    exposed = {name for name, service in model["services"].items() if service.get("ports")}
    assert exposed == {"web"}


def test_no_service_is_privileged_or_mounts_docker_socket() -> None:
    model = yaml.safe_load(Path("compose.yaml").read_text())
    for service in model["services"].values():
        assert service.get("privileged") is not True
        assert all("/var/run/docker.sock" not in str(v) for v in service.get("volumes", []))
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest tests/contracts/test_compose_security.py -q`

Expected: FAIL because `compose.yaml` does not exist.

- [ ] **Step 3: Implement production and development compositions**

Production publishes only `web:3000`. API and data services use `expose` on `agentos_private`. Add health checks, restart policies, read-only root filesystems where supported, dropped Linux capabilities, and named volumes. The development override may publish localhost-only ports such as `127.0.0.1:8000:8000`.

Initialize `CREATE EXTENSION IF NOT EXISTS vector;`. Do not embed passwords in YAML; require Compose secrets/environment interpolation.

- [ ] **Step 4: Add deterministic smoke validation**

`scripts/compose_smoke.sh` must run `docker compose config --quiet`, start services, wait with a bounded 120-second loop for health, request liveness through the web/API route, print `docker compose ps` on failure, and always tear down containers while retaining named volumes unless `PURGE=1`.

- [ ] **Step 5: Validate the configuration and security contract**

Run: `docker compose config --quiet && pytest tests/contracts/test_compose_security.py -q`

Expected: configuration valid and 2 tests pass.

- [ ] **Step 6: Run the smoke test**

Run: `bash scripts/compose_smoke.sh`

Expected: all five services become healthy and the script exits 0.

- [ ] **Step 7: Commit**

```bash
git add compose.yaml infra services/api/Dockerfile apps/web/Dockerfile scripts tests/contracts
git commit -m "feat(infra): add private Compose deployment"
```

---

### Task 4: Authentication Persistence and Cryptography

**Files:**
- Create: `services/api/alembic.ini`
- Create: `services/api/alembic/env.py`
- Create: `services/api/alembic/versions/0001_auth_and_audit.py`
- Create: `services/api/src/agentos/auth/models.py`
- Create: `services/api/src/agentos/crypto.py`
- Create: `services/api/tests/auth/test_crypto.py`
- Create: `services/api/tests/auth/test_models.py`

**Interfaces:**
- Consumes: `Settings.master_key`, SQLAlchemy base/session.
- Produces: models `AdminUser`, `Session`, `TotpEnrollment`, `RecoveryCode`, `AuditEvent`; `hash_password()`, `verify_password()`, `hash_token()`, `encrypt_secret()`, and `decrypt_secret()`.

- [ ] **Step 1: Write failing cryptography tests**

```python
def test_password_hash_is_argon2id_and_verifies():
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "correct horse battery staple") is True
    assert verify_password(encoded, "wrong") is False


def test_secret_ciphertext_does_not_contain_plaintext(cipher):
    encrypted = cipher.encrypt_secret(b"totp-secret")
    assert b"totp-secret" not in encrypted
    assert cipher.decrypt_secret(encrypted) == b"totp-secret"
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `pytest services/api/tests/auth/test_crypto.py -q`

Expected: FAIL because cryptographic functions do not exist.

- [ ] **Step 3: Implement focused cryptographic primitives**

Use `argon2.PasswordHasher(type=Type.ID)` for passwords and recovery codes. Use HMAC-SHA-256 with the session pepper for opaque session-token hashes. Use `cryptography.fernet.Fernet` behind a `SecretCipher` class for encrypted TOTP material; never log inputs or outputs.

- [ ] **Step 4: Write model and migration tests**

Assert a fresh migration creates one-user-constrained `admin_users`, `sessions`, `totp_enrollments`, `recovery_codes`, and append-oriented `audit_events`. Assert plaintext columns named `password`, `token`, `totp_secret`, or `recovery_code` do not exist.

- [ ] **Step 5: Implement models and migration**

Store `password_hash`, `token_hash`, `encrypted_secret`, and `code_hash`. Sessions include `expires_at`, `revoked_at`, `last_seen_at`, IP hash, and user-agent hash. Audit events include request ID, actor ID, action, target type/ID, outcome, safe metadata JSON, and timestamp.

- [ ] **Step 6: Run migration and focused tests**

Run: `alembic -c services/api/alembic.ini upgrade head && pytest services/api/tests/auth/test_crypto.py services/api/tests/auth/test_models.py -q`

Expected: migration succeeds and all tests pass.

- [ ] **Step 7: Commit**

```bash
git add services/api
git commit -m "feat(auth): add secure authentication persistence"
```

---

### Task 5: Admin Bootstrap, TOTP Enrollment, and Sessions API

**Files:**
- Create: `services/api/src/agentos/auth/schemas.py`
- Create: `services/api/src/agentos/auth/totp.py`
- Create: `services/api/src/agentos/auth/service.py`
- Create: `services/api/src/agentos/audit/service.py`
- Create: `services/api/src/agentos/api/routes/auth.py`
- Create: `services/api/tests/api/test_auth_flow.py`
- Create: `scripts/bootstrap_admin.py`

**Interfaces:**
- Consumes: auth/audit models and crypto primitives.
- Produces: `POST /auth/login`, `POST /auth/totp/enroll`, `POST /auth/totp/confirm`, `POST /auth/totp/verify`, `POST /auth/recovery`, `POST /auth/logout`, `GET /auth/me`, and idempotent CLI bootstrap.

- [ ] **Step 1: Write the failing end-to-end API test**

```python
async def test_admin_must_complete_totp_before_authenticated(api, admin):
    login = await api.post("/auth/login", json={"email": admin.email, "password": "valid-password"})
    assert login.status_code == 200
    assert login.json()["next"] == "totp_enrollment"

    enrollment = await api.post("/auth/totp/enroll")
    assert enrollment.status_code == 200
    assert enrollment.json()["otpauth_uri"].startswith("otpauth://totp/AgentOS:")

    code = current_totp(enrollment.json()["test_secret"])
    confirmed = await api.post("/auth/totp/confirm", json={"code": code})
    assert confirmed.status_code == 200
    assert len(confirmed.json()["recovery_codes"]) == 10

    me = await api.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["totp_enabled"] is True
```

The production response must never expose `test_secret`; the fixture enables a test-only dependency that returns it outside the serialized HTTP model.

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest services/api/tests/api/test_auth_flow.py::test_admin_must_complete_totp_before_authenticated -q`

Expected: FAIL because auth routes do not exist.

- [ ] **Step 3: Implement bootstrap and staged authentication**

The bootstrap command creates the sole administrator only when none exists and reads its password from an interactive prompt or `AGENTOS_BOOTSTRAP_PASSWORD_FILE`, never a command-line argument. Login creates a five-minute pre-auth session. Confirming TOTP rotates it into a full session and returns ten recovery codes exactly once.

- [ ] **Step 4: Implement cookie and session rules**

Generate 32 random bytes for the opaque token, persist only its HMAC hash, rotate on privilege elevation, use absolute and idle expiry, and set cookie attributes `HttpOnly`, `Secure` in production, `SameSite=Strict`, and `Path=/`. Logout revokes the server session before clearing the cookie.

- [ ] **Step 5: Add negative-path tests**

Test wrong password, invalid/replayed TOTP in the accepted window, expired pre-auth session, revoked session, consumed recovery code, second-user bootstrap rejection, and rate-limit response. Assert audit events exist without secret-bearing metadata.

- [ ] **Step 6: Run focused tests**

Run: `pytest services/api/tests/api/test_auth_flow.py -q`

Expected: all positive and negative authentication tests pass.

- [ ] **Step 7: Commit**

```bash
git add services/api scripts/bootstrap_admin.py
git commit -m "feat(auth): implement password and TOTP login"
```

---

### Task 6: Next.js Login, Enrollment, and Protected Shell

**Files:**
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/globals.css`
- Create: `apps/web/app/(auth)/login/page.tsx`
- Create: `apps/web/app/(auth)/enroll/page.tsx`
- Create: `apps/web/app/(dashboard)/layout.tsx`
- Create: `apps/web/app/(dashboard)/page.tsx`
- Create: `apps/web/app/api/auth/[...path]/route.ts`
- Create: `apps/web/components/auth/login-form.tsx`
- Create: `apps/web/components/auth/totp-form.tsx`
- Create: `apps/web/lib/api/client.ts`
- Create: `apps/web/lib/auth/session.ts`
- Create: `apps/web/tests/auth-flow.test.tsx`
- Create: `apps/web/e2e/login.spec.ts`

**Interfaces:**
- Consumes: Task 5 auth endpoints and opaque cookie.
- Produces: accessible login/TOTP/recovery UI, protected dashboard shell, and same-origin server proxy.

- [ ] **Step 1: Write failing component tests**

```tsx
it("continues from password to TOTP without storing credentials", async () => {
  render(<LoginForm authenticate={authenticateStub} />)
  await user.type(screen.getByLabelText(/email/i), "admin@example.com")
  await user.type(screen.getByLabelText(/password/i), "valid-password")
  await user.click(screen.getByRole("button", { name: /continue/i }))
  expect(await screen.findByLabelText(/authentication code/i)).toBeVisible()
  expect(window.localStorage.length).toBe(0)
})
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pnpm --filter @agentos/web test -- auth-flow.test.tsx`

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement the auth UI and same-origin proxy**

Use server components for session-aware layouts and client components only for forms. Proxy `/api/auth/*` to the internal API without exposing its private address to the browser. Do not store session or pre-auth material in localStorage/sessionStorage. Show recovery codes once with explicit download/copy acknowledgement.

- [ ] **Step 4: Implement the protected Mission Control shell**

Unauthenticated access redirects to `/login`. A pre-auth session redirects to the correct TOTP step. The initial dashboard shows honest empty states for Tasks, Running Agents, Pending Approvals, and Provider Health; do not fabricate metrics.

- [ ] **Step 5: Add browser tests**

Playwright covers password login, enrollment QR/manual key, TOTP confirmation, recovery-code acknowledgement, logout, invalid code, session expiry, and protected-route redirect. Capture no passwords or TOTP secrets in traces.

- [ ] **Step 6: Run frontend verification**

Run: `pnpm --filter @agentos/web lint && pnpm --filter @agentos/web typecheck && pnpm --filter @agentos/web test && pnpm --filter @agentos/web build`

Expected: all commands exit 0.

- [ ] **Step 7: Commit**

```bash
git add apps/web
git commit -m "feat(web): add secure admin login and dashboard shell"
```

---

### Task 7: Audit Visibility and Security Regression Coverage

**Files:**
- Create: `services/api/src/agentos/api/routes/audit.py`
- Create: `services/api/tests/api/test_audit.py`
- Create: `apps/web/app/(dashboard)/audit/page.tsx`
- Create: `apps/web/components/audit/audit-table.tsx`
- Create: `apps/web/tests/audit-table.test.tsx`

**Interfaces:**
- Consumes: authenticated admin dependency and `AuditEvent` records.
- Produces: paginated `GET /audit/events?cursor=&action=&outcome=` and a read-only dashboard view.

- [ ] **Step 1: Write failing audit API tests**

```python
async def test_audit_requires_full_session(api):
    response = await api.get("/audit/events")
    assert response.status_code == 401


async def test_audit_never_serializes_sensitive_metadata(authenticated_api, seeded_audit):
    response = await authenticated_api.get("/audit/events")
    text = response.text.lower()
    assert "password" not in text
    assert "totp_secret" not in text
    assert "session_token" not in text
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest services/api/tests/api/test_audit.py -q`

Expected: FAIL because the route does not exist.

- [ ] **Step 3: Implement cursor pagination and metadata allowlisting**

Return newest-first audit records through a stable `(created_at, id)` cursor. Serialize only allowlisted safe metadata keys. Record access to audit history as its own event without recursively exposing secrets.

- [ ] **Step 4: Implement and test the read-only table**

The table exposes timestamp, action, target, outcome, request ID, and safe detail. It supports action/outcome filters and cursor navigation. It provides no edit or delete operation.

- [ ] **Step 5: Run backend and frontend focused tests**

Run: `pytest services/api/tests/api/test_audit.py -q && pnpm --filter @agentos/web test -- audit-table.test.tsx`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/api apps/web
git commit -m "feat(audit): expose secure activity history"
```

---

### Task 8: CI, Operator Documentation, and Acceptance Test

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `README.md`
- Create: `docs/operations/ubuntu-deployment.md`
- Create: `docs/operations/cloudflare-tunnel.md`
- Create: `docs/operations/backup-restore.md`
- Create: `scripts/backup.sh`
- Create: `scripts/restore.sh`
- Create: `tests/acceptance/test_foundation_acceptance.py`

**Interfaces:**
- Consumes: all outputs from Tasks 1–7.
- Produces: repeatable CI, Ubuntu installation/runbook, Cloudflare Tunnel mapping, encrypted backup/restore commands, and the Plan 1 acceptance gate.

- [ ] **Step 1: Write the failing acceptance test**

```python
def test_foundation_acceptance(running_stack, browser, database):
    admin = running_stack.bootstrap_admin()
    browser.login_and_enroll_totp(admin)
    browser.assert_dashboard_visible()
    browser.logout()
    browser.assert_dashboard_requires_login()
    assert database.audit_actions() >= {
        "auth.login.succeeded",
        "auth.totp.enrolled",
        "auth.logout",
    }
```

- [ ] **Step 2: Run the acceptance test and verify failure**

Run: `pytest tests/acceptance/test_foundation_acceptance.py -q`

Expected: FAIL until the stack fixture and operator workflow are connected.

- [ ] **Step 3: Implement CI with service-backed tests**

Define separate jobs for backend lint/type/test, frontend lint/type/test/build, Compose contracts, dependency audit, container build/scan, and acceptance smoke. Pin actions to commit SHAs and give the workflow read-only permissions except where checkout requires contents read.

- [ ] **Step 4: Write exact Ubuntu and Cloudflare operations**

Document prerequisites, secret generation, `.env` placement and permissions, first bootstrap, migrations, startup, health checks, upgrades, rollback, and troubleshooting. Cloudflare maps the public hostname only to `web:3000`; no instructions expose API or database ports.

- [ ] **Step 5: Implement encrypted backup and guarded restore**

Backup streams `pg_dump` plus MinIO object export into a timestamped archive and encrypts it with an operator-provided age recipient. Restore requires an explicit archive path, validates decryption and checksums before mutation, refuses a running production stack, and prints the exact target before requiring interactive confirmation.

- [ ] **Step 6: Execute the full verification matrix**

Run:

```bash
ruff check services/api tests
mypy services/api/src
pytest -q
pnpm lint
pnpm typecheck
pnpm test
pnpm build
docker compose config --quiet
bash scripts/compose_smoke.sh
pytest tests/acceptance/test_foundation_acceptance.py -q
```

Expected: every command exits 0; acceptance proves login, TOTP enrollment, dashboard protection, logout, and audit events.

- [ ] **Step 7: Inspect public port bindings**

Run: `docker compose ps --format json`

Expected: only `web` has a published host port; PostgreSQL, Redis, MinIO, and API have no public binding.

- [ ] **Step 8: Commit**

```bash
git add .github README.md docs/operations scripts tests/acceptance
git commit -m "ci: verify AgentOS foundation deployment"
```

## Plan 1 Completion Gate

Before starting Plan 2, demonstrate all of the following on the Compose stack:

- A new installation can create only one administrator through the guarded bootstrap process.
- Password login cannot produce a full session until TOTP is enrolled and verified.
- Recovery codes appear once, are stored only as hashes, and are consumed once.
- Protected pages and APIs reject missing, pre-auth, expired, and revoked sessions.
- Security-relevant actions produce redacted audit events.
- Only the web entry point is published in production Compose.
- PostgreSQL, Redis, and MinIO readiness failures are visible without exposing credentials.
- Backup validation succeeds and a restore rehearsal succeeds against a disposable stack.
- Lint, type checks, unit/integration tests, production builds, container checks, smoke tests, and the acceptance test pass.

After this gate, write Plan 2 for universal tasks, Kanban, durable runs, workers, approvals, and live events using the domain contracts in the approved specification.
