# Task 6 Report: Next.js Login, Enrollment, and Protected Shell

## Status

**DONE_WITH_CONCERNS**

The accessible password, TOTP enrollment/verification, recovery, logout, protected dashboard, and same-origin auth proxy flows are implemented. Component/contract tests, frontend static checks, production build, and the accepted Task 5 backend auth suite pass. The Playwright suite is present and discovered, but its browser runtime could not be downloaded in this environment, so browser execution is **Cannot Verify**.

## Files

- Replaced the starter `apps/web/src/app` routes with the App Router structure under `apps/web/app`.
- Added auth pages, dashboard layout/page, global styling, login/TOTP/logout components, typed API client, session resolution, and protected-route decisions.
- Added the strict allowlisted proxy at `apps/web/app/api/auth/[...path]/route.ts`.
- Added Vitest setup and component/contract coverage in `apps/web/tests`.
- Added Playwright configuration, six browser scenarios, and a private test fixture API in `apps/web/e2e`.
- Updated `apps/web/package.json`, `apps/web/vitest.config.ts`, and `pnpm-lock.yaml` for pinned test and QR dependencies.

## Security Review

- Browser auth calls use only same-origin `/api/auth/*` paths; the internal API address is server-only.
- Proxy paths are limited to the exact Task 5 routes and response shapes.
- All proxy mutations require an exact `Origin` match and reject hostile `Sec-Fetch-Site` values. Tests independently cover Origin rejection, Fetch Metadata rejection, allowed forwarding, and replacement `Set-Cookie` propagation.
- Session and pre-auth credentials are carried only by opaque HTTP-only cookies. No auth material is written to local storage or session storage.
- Passwords, TOTP values, provisioning secrets, recovery codes, and session tokens are not logged. Playwright trace, video, and screenshot capture are disabled.
- Recovery codes are rendered only from the one-time confirmation response, offer explicit copy/download actions, require saved-code acknowledgement, and are cleared before leaving enrollment.
- The dashboard reports empty Tasks, Running Agents, Pending Approvals, and Provider Health states without fabricated counts.

## Verification

- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web lint`
  - Exit 0; ESLint reported no errors or warnings.
- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web typecheck`
  - Exit 0; `tsc --noEmit` passed.
- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web test`
  - Exit 0; 2 files and 12 tests passed.
- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web build`
  - Exit 0; Next.js production compilation, TypeScript, and route generation passed for `/`, `/login`, `/enroll`, and `/api/auth/[...path]`.
- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web exec playwright test --list`
  - Exit 0; 6 tests discovered in `login.spec.ts`.
- `uv run --frozen --project services/api pytest services/api/tests/api/test_auth_flow.py -q`
  - Exit 0; 22 tests passed.
- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 install --frozen-lockfile --offline`
  - Exit 0; the lockfile was current and all packages resolved from the local store.
- `make test`
  - Exit 0; 12 frontend tests and the complete 93-test Python/contract suite passed.
- `git diff --check`
  - Exit 0; no whitespace errors.

### Browser runtime: Cannot Verify

Command attempted once, then stopped rather than retrying indefinitely:

`COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web exec playwright install chromium`

Playwright attempted Chrome for Testing `153.0.8010.12` (Chromium v1243) from `https://cdn.playwright.dev/builds/cft/153.0.8010.12/linux64/chrome-linux64.zip` and failed with HTTP 502. The response reported `[Errno 111] Connection refused`. Therefore the six browser scenarios could not be launched in this environment.

## Commit

`feat(web): add secure admin login and dashboard shell` (this Task 6 commit; final SHA is reported by the task runner after commit creation).

## Self-review

- Verified accepted Task 5 contracts directly before defining frontend types and proxy allowlists.
- Verified the proxy forwards only cookie, content type, and user-agent request headers, and only cache control, content type, retry-after, and set-cookie response headers.
- Avoided a redundant enrollment request by reusing the server-side enrollment response when rendering `/enroll`.
- Confirmed all newly added interactions have observable tests and all final non-browser checks were rerun after the last production change.

## Concerns

- The full Playwright runtime result remains **Cannot Verify** until Chromium is available; test discovery/configuration succeeds and all six required scenarios are committed.
- Task 5 exposes no non-mutating pre-auth introspection endpoint. Server-side pre-auth stage resolution therefore uses the accepted enrollment endpoint: `200` identifies pending enrollment and `409` identifies TOTP verification. The enrollment response is reused to avoid a duplicate request on the enrollment page.

## Reconciliation After Environment Rollback

The Task 6 brief, this report, and the SDD ledger rulings were re-read after the previously reviewed Task 6 commit object disappeared. The uncommitted changes were preserved. Verification covered the canonical `AGENTOS_PUBLIC_ORIGIN` CSRF contract, read-only staged `/auth/state`, propagated auth-service failures, accessible clipboard success/failure feedback, `.env.example`/Compose consistency, and proxy/API contract coverage.

### Fresh evidence

- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web test` — 2 files, 16 tests passed.
- `uv run --offline --frozen --project services/api pytest services/api/tests/api/test_auth_flow.py -q` — 23 tests passed.
- `uv run --offline --frozen --project services/api pytest -q` — 94 tests passed, including Compose and repository environment contracts.
- `make lint` — web ESLint and backend Ruff passed.
- `make typecheck` — frontend `tsc --noEmit` and backend mypy passed (`14 source files`).
- `make test` — frontend 16 tests and backend 94 tests passed.
- `make build` — Next.js production build passed; routes generated for `/`, `/login`, `/enroll`, and `/api/auth/[...path]`.
- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web exec playwright test --list` — all 6 browser scenarios discovered.
- `git diff --check` — passed with no whitespace errors.

The browser runtime remains **Cannot Verify** because Chromium is unavailable in this executor; discovery and configuration remain verified. The only source changes needed during reconciliation were stale enrollment-shape fixtures, import/line formatting, and the environment-template contract update required by `AGENTOS_PUBLIC_ORIGIN`. No Task 7 files or behavior were added.
