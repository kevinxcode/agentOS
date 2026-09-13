# Task 7 Report: Audit Visibility and Security Regression Coverage

## Status

DONE_WITH_CONCERNS

## Summary

- Added full-session-protected `GET /audit/events` with fixed 50-event pages,
  stable newest-first `(created_at, id)` ordering, opaque validated cursors, and
  exact `success | failure | denied | error` outcome filtering.
- Added centralized safe-metadata key allowlisting and value redaction for URL
  query/fragment data, API keys, credential assignments, Bearer payloads, JWTs,
  callback codes, and standalone 22-character URL-safe recovery candidates.
  Ordinary prose such as `Bearer authentication is disabled` and
  `customer #42 submitted a question` remains readable.
- Materialized each response before appending `audit.events.viewed`, preventing
  the access event from recursively appearing in the response that created it.
- Added a read-only RSC audit page, validated server fetcher, same-origin audit
  proxy, accessible table/filter/pagination controls, route-aware navigation,
  and a mobile Audit navigation entry.
- Added an explicit URL cursor trail for Previous navigation. Appends retain the
  last 50 entries, filters survive Next/Previous, Previous stays functional past
  page 51, and no code uses browser/router back navigation.
- Keyed client filter state by all URL-derived state so RSC navigation, browser
  history, cursor changes, and Clear cannot leave controls out of sync.

## Files Changed

- `services/api/src/agentos/api/routes/audit.py`
- `services/api/src/agentos/api/app.py`
- `services/api/src/agentos/audit/service.py`
- `services/api/tests/api/test_audit.py`
- `apps/web/app/(dashboard)/audit/page.tsx`
- `apps/web/app/(dashboard)/layout.tsx`
- `apps/web/app/api/audit/events/route.ts`
- `apps/web/components/audit/audit-table.tsx`
- `apps/web/components/navigation/primary-navigation.tsx`
- `apps/web/lib/audit/server.ts`
- `apps/web/lib/audit/types.ts`
- `apps/web/tests/audit-table.test.tsx`
- `apps/web/tests/setup.ts`
- `apps/web/app/globals.css`

## TDD Evidence

- Backend RED: `services/api/.venv/bin/pytest
  services/api/tests/api/test_audit.py -q` — `4 failed`; every failure was the
  expected missing-route `404`.
- Backend GREEN: the same focused command — `4 passed in 1.33s`.
- Frontend RED: `corepack pnpm@10.15.1 --filter @agentos/web test --
  audit-table.test.tsx` — failed to resolve the not-yet-created audit proxy.
- Frontend GREEN: the same focused command — all 3 files and 27 tests passed.
- History-sync RED: after adding the cursor-only RSC-navigation regression, the
  focused frontend run reported `1 failed, 26 passed`; an unsubmitted action
  draft remained visible.
- History-sync GREEN: keying filter state by action, outcome, cursor, and trail
  produced all 3 files and 27 tests passing.

## Final Verification Evidence

- `services/api/.venv/bin/pytest services/api/tests -q` — `90 passed in 44.50s`.
- `corepack pnpm@10.15.1 --filter @agentos/web test` — 3 files and 27 tests
  passed.
- `services/api/.venv/bin/ruff check services/api/src services/api/tests` —
  `All checks passed!`.
- `services/api/.venv/bin/mypy services/api/src` —
  `Success: no issues found in 15 source files`.
- `corepack pnpm@10.15.1 --filter @agentos/web lint` — exit 0 with no ESLint
  findings.
- `corepack pnpm@10.15.1 --filter @agentos/web typecheck` — `tsc --noEmit`
  exited 0.
- `corepack pnpm@10.15.1 --filter @agentos/web build` — Next.js 16.3.4
  compiled, typechecked, generated pages, and emitted dynamic `/audit` and
  `/api/audit/events` routes successfully.
- `corepack pnpm@10.15.1 --filter @agentos/web exec playwright test --list` —
  6 tests discovered in `login.spec.ts`.
- `git diff --check` — exit 0 before the report was added; rerun after the
  report is recorded below.

## Coverage Highlights

- Anonymous and pre-auth sessions receive 401; only a current full session can
  view audit data.
- Stable equal-timestamp paging covers 101 records, insertions between page
  requests, non-overlap, and terminal-cursor behavior.
- Unsupported `rate_limited`, empty outcomes, explicit empty cursors, and
  malformed cursors receive the same sanitized 422 validation response.
- Metadata tests cover top-level key removal, path and URL query/fragment
  stripping, every required secret shape, and both required ordinary-prose
  preservation examples.
- Server and proxy tests cover cookie forwarding, exact URLSearchParams
  encoding, `cache: no-store`, no-store responses, server-page 401 redirect,
  malformed successful upstream payloads, and generic responses that do not
  expose `http://api:8000`.
- UI tests cover read-only columns, absence of edit/delete operations, native
  disabled Previous/Next behavior, full URL/filter synchronization, a bounded
  52-page cursor history, `aria-current`, and mobile Audit access.

## Concerns

- Playwright discovery passed, but this task did not execute the browser suite;
  Chromium remains unavailable in the reconciled executor per the accepted
  Task 6 report.
- Backend integration coverage uses the repository's real SQLAlchemy path over
  SQLite. A live PostgreSQL acceptance run remains a promotion-time check.

## Fix Round: RSC-safe Cursor Trail (2026-09-12)

- Root cause: the server `AuditPage` imported `parseCursorTrail` from the
  `'use client'` audit table module. Next's production RSC bundle converted
  that named import into a client-reference stub, so a successful `/audit`
  render could throw when the server called it.
- Moved `CursorTrail`, `MAX_CURSOR_TRAIL`, parsing, and serialization into
  `apps/web/lib/audit/cursor.ts`, a server-safe pure module imported by both
  `AuditPage` and the client audit table. Serialization still bounds history
  to the last 50 entries, including navigation beyond page 51.
- Added a successful server-page regression that renders the real `AuditPage`
  and actual `AuditTable` with a cursor trail; it does not mock a client
  export. TDD RED failed to resolve the new module; GREEN passed after the
  extraction.
- Focused frontend test: `corepack pnpm@10.15.1 --filter @agentos/web test -- audit-table.test.tsx` — 3 files and 28 tests passed.
- Full frontend tests: `corepack pnpm@10.15.1 --filter @agentos/web test` — 3 files and 28 tests passed.
- Frontend lint/typecheck passed; Playwright discovery found 6 tests.
- Production proof: `AGENTOS_API_URL=http://127.0.0.1:4101 corepack pnpm@10.15.1 --filter @agentos/web build` — Next.js compiled and emitted dynamic `/audit` and `/api/audit/events` routes. The generated server bundle contains cursor parsing and no `parseCursorTrail` client-reference stub.
- Backend recheck: `services/api/.venv/bin/pytest services/api/tests -q` — 90 passed; Ruff passed; mypy reported no issues. Existing coverage continues to verify bounded paging, exact outcome enum filtering/display inputs, secret-safe non-destructive redaction, and server/proxy cookie/error/no-store behavior.
- `git diff --check` passed. Playwright browser execution and live PostgreSQL remain promotion-time concerns recorded above.
