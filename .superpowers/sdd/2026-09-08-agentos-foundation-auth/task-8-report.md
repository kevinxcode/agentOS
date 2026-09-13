# Task 8 report — CI, operations and foundation acceptance

## Status

DONE_WITH_CONCERNS. Implementation and local verification delivered; the Plan 1
production completion gate is **not demonstrated**. Do not start/promote Plan 2
on the strength of SQLite/unit checks alone.

## Delivered

- Six independent GitHub Actions gates: backend lint/type/unit + migrated live
  PostgreSQL acceptance; frontend lint/type/unit/production build + Chromium over
  the controlled auth service; Compose/shell/workflow contracts; locked dependency
  audits; production image builds and high/critical vulnerability scans; real
  Compose/Chromium acceptance. Actions use full commit SHAs, global permissions
  are contents:read, checkout credentials are not persisted, no artifacts containing
  recovery codes or session evidence are uploaded, and scanner failures are blocking.
- README accurately limits the milestone to foundation/authentication/audit.
  Ubuntu runbook covers protected secret generation, first migration/bootstrap,
  startup, readiness, published ports, upgrades, rollback and troubleshooting.
  Cloudflare instructions route exclusively to web:3000, include a separate
  egress-enabled connector and preserve the private service network.
- New private, no-overwrite environment generator uses independent secrets and a
  Fernet-compatible key. The existing API-only .env.example remains unchanged.
- API image includes Alembic configuration/migrations, bootstrap, and backup helper
  so documented container commands can actually resolve their entrypoints.
- Versioned PostgreSQL + MinIO current-object backup with age encryption, private
  temporary staging, nested checksums and safe member validation. Object keys are
  JSON values and are never extracted as paths. The backup helper preserves current
  bytes/content types, not bucket policies/IAM/version history.
- Restore requires absolute archive/identity/env paths, a restricted explicit
  project name, protected env permissions, a stopped writer stack, successful age
  decryption/checksum/manifest validation and a real interactive confirmation.
  It rechecks writers, refuses nonempty database/bucket targets, never drops tables,
  deletes objects, or uses pg_restore --clean. Host AGENTOS variables are removed
  so inherited credentials cannot override the explicitly selected env file.
- Disposable smoke names are unique; the smoke scripts reject production project
  selection, explicitly select production Compose, and retain named volumes rather
  than offering an automatic purge. Added live Compose ps JSON port validation.
- Layered acceptance: real migrated SQLite + HTTP locally; fresh explicit
  agentos_test PostgreSQL in CI; opt-in full Compose/real browser login/enrollment,
  dashboard protection, Audit page, logout and database audit checks.

## TDD / regression evidence

- First `pytest tests/acceptance -q`: 4 failed, 3 passed, 1 skipped, 1 error.
  Missing backup scripts/archive helper caused intended failures; foundation
  setup failed because its new stack fixture was not connected. The three negative
  archive cases initially passed only because the helper was absent; subsequent
  successful roundtrip/guard tests ensure the helper is genuinely exercised.
- After initial wiring: 7 passed, 1 skipped, 1 error exposed an incorrect test
  assumption about duplicate bootstrap: a different email raises BootstrapError,
  rather than returning false. The fixture now checks both same-email idempotence
  and different-email refusal, plus the database uniqueness constraint.
- Initial workflow contract: 1 failed, 4 passed (workflow absent); added workflow.
- Production-project smoke regression: 1 failed, 5 passed; production project was
  not refused before Docker invocation. Added the disposable-project guard.
- Inherited-environment regression: 1 failed, 10 passed; inherited database URL
  remained set. Explicit-target setup now unsets all AGENTOS variables.
- Malformed object metadata regression: 1 failed; a checksummed record missing
  content_type was accepted. Schema validation now rejects it before extraction.
- Final acceptance suite: 20 passed, 1 explicitly skipped Compose/browser gate.
  Additional behavioral tests cover archive corruption, symlink/traversal members,
  invalid arguments, running writers, decryption/checksum/confirmation failures,
  private output modes, no-overwrite generation, unique backup publication, and
  real archive validation around controlled Docker/age boundary fakes. The age fake
  deliberately does not implement encryption and is not evidence of interoperability.

## Exact verification results (2026-09-12)

Commands run from the task worktree; Python tools used services/api/.venv/bin and
pnpm used project-local COREPACK_HOME plus corepack pnpm@10.15.1 per the ledger.

| Check | Result |
|---|---|
| `services/api/.venv/bin/ruff check services/api tests` | PASS, All checks passed |
| `services/api/.venv/bin/ruff check services/api tests scripts` | PASS |
| `services/api/.venv/bin/mypy services/api/src` | PASS, no issues in 15 source files |
| `services/api/.venv/bin/pytest -q` | PASS, 118 passed, 1 skipped in 24.97s |
| `corepack pnpm@10.15.1 lint` | PASS |
| `corepack pnpm@10.15.1 typecheck` | PASS |
| `corepack pnpm@10.15.1 test` | PASS, 3 files / 28 tests |
| `corepack pnpm@10.15.1 build` | PASS, Next.js 16.3.4 compiled/typechecked/generated all routes |
| `pytest tests/acceptance/test_foundation_acceptance.py -q` | PASS locally: 1 passed, 1 explicit skip in 2.08s |
| `pytest tests/acceptance -q` | PASS: 20 passed, 1 explicit skip in 3.02s |
| `pytest tests/acceptance/test_delivery_contracts.py -q` | PASS: 6; YAML parsed, permissions/job/action-pin and live-port contracts checked |
| `for script in scripts/*.sh; do bash -n "$script"; done` | PASS for every script |
| `node --check apps/web/e2e/foundation.mjs` | PASS |
| `playwright test --list` | PASS: six existing browser tests discovered |
| `playwright test` | BLOCKED: all six launch attempts failed because Chromium executable is absent |
| `docker compose config --quiet` | Cannot Verify: Docker executable absent (127) |
| `bash scripts/compose_smoke.sh` | Cannot Verify: explicit Docker-required failure (1) |
| `docker compose ps --format json` | Cannot Verify: Docker executable absent (127) |
| `bash scripts/acceptance_smoke.sh` | Cannot Verify: explicit Docker-required failure (1) |
| Explicit localhost PostgreSQL acceptance URL | Cannot Verify: migration connection refused at 127.0.0.1:5432; 1 error, 1 skip |
| `shellcheck -x scripts/*.sh` | Cannot Verify: executable absent (127) |
| `uv tool run shellcheck-py==0.10.0.1 --version` | Cannot Verify: package download timed out after retries |
| `actionlint .github/workflows/ci.yml` | Cannot Verify: executable absent (127); YAML/security contract tests are not full actionlint |
| `age --version` | Cannot Verify: executable absent (127) |
| `git diff --check` | PASS; rerun after report and before commit |

The browser attempt generated development-only Next agent files and failure
artifacts. Generated agent files were removed, production build restored next-env
types, and test-results/playwright-report are now ignored. No application or user
data was deleted; failure test output remains local and uncommitted.

## Interpretations and remaining concerns

1. The task's pseudocode names auth.login.succeeded. Existing Task 5's established
   contract is action=auth.login with outcome=success; acceptance asserts the
   structured pair without silently renaming production audit events.
2. Docker/runtime hardening and private port bindings from Task 3, PostgreSQL
   migration/constraint/timezone behavior from Task 4, and real Chromium behavior
   from Task 6 remain unverified here. CI explicitly exercises these paths, but
   this task did not run a GitHub Actions workflow or fabricate its results.
3. Dependency advisory lookups, container scanning and image builds need CI network
   access. Their success is not claimed; existing pinned dependencies may produce
   blocking vulnerability findings that require a separately reviewed upgrade.
4. The backup implementation intentionally uses private plaintext staging while
   building/verifying the combined archive. Operators need encrypted staging media
   if plaintext at rest is prohibited. Backup consistency requires stopped writers,
   including writers outside Compose; the scripts cannot enforce external processes
   or prevent an operator concurrently restarting a service.
5. A **real age decrypt/verify and fresh-target restore rehearsal is mandatory** on
   the documented Ubuntu host. No successful real restore is claimed. The fix-round
   behavior below removes a confirmed fresh target after failed mutation, but its
   real Docker-volume behavior remains a host gate. Preserve the original master
   key/session pepper separately.
6. The base web port publishes on all host interfaces. Documentation calls out
   Docker-aware firewall/loopback override requirements; no private service is
   published by base Compose. Real external reachability, Cloudflare/TLS routing,
   and maintenance dependency-failure checks still require a host rehearsal.
7. Therefore the Plan 1 completion gate is OPEN, not satisfied. Keep promotion and
   Plan 2 blocked until CI, real-browser HTTPS and encrypted restore evidence exist.

## Fix round 1 — Important review findings (2026-09-13)

Status: ADDRESSED_IN_CODE; runtime promotion gate remains OPEN.

### Changes

1. Added `scripts/agentos-compose.sh` and moved production, backup/restore,
   Compose-smoke and acceptance-smoke invocations onto an allowlisted process
   environment. `AGENTOS_*` and Compose override variables inherited from the
   operator shell cannot outrank the selected mode-0600/0400 `--env-file`.
   Ubuntu migration/bootstrap/start/health commands use the wrapper; the tunnel
   runbook uses an equivalent allowlisted command for its external Compose file.
2. Exercised the confirmed restore mutation path through deterministic Docker,
   age and object-store boundary fakes. Restore now verifies both targets are empty,
   restores PostgreSQL with `--single-transaction` before objects, never starts API,
   web or workers, and removes only the confirmed fresh project's volumes when a
   database or object import fails. Success retains the rehearsal volumes for
   operator verification. Interactive confirmation and the running-app refusal are
   unchanged; no real destructive restore was performed in this executor.
3. Unified public-origin normalization. The environment generator and web validator
   lowercase hostnames, remove an optional trailing slash, omit HTTPS `:443` and HTTP
   `:80`, preserve non-default ports, require HTTPS except for loopback-only
   disposable tests, and accept both `localhost` and numeric loopback. CI's Compose
   config smoke now deliberately
   generates from `https://agentos.example.com:443/`; Python and web regressions
   assert the same canonical value, and both operator runbooks document it.
4. Re-reviewed `.github/workflows/ci.yml` statically. All `uses:` entries remain
   40-character lowercase SHA references; workflow permissions remain
   `contents: read`; no step/job uses `continue-on-error`; the final acceptance job
   needs all five prerequisite jobs. Executable contracts assert PostgreSQL health
   gating, real Chromium install/test commands, Docker builds, blocking Trivy
   `--exit-code 1`, and both Compose acceptance scripts. No obvious command/config
   mismatch remained after routing Compose config through the protected-env wrapper.

### TDD evidence

- Initial focused Python regression run: **6 failed, 20 passed**. Failures proved the
  operator wrapper was absent, default-port origins were rejected/not normalized,
  restore imported objects before PostgreSQL, and no post-mutation rollback existed.
- New object-target preflight test initially failed with `AttributeError` because
  `check_empty_objects` did not exist.
- Initial web regression run: **2 failed, 28 passed**; both default-port/case/trailing
  slash inputs were rejected by the old strict equality check. A parity follow-up
  then failed **1 of 31** because web still accepted remote HTTP while the generator
  rejected numeric loopback HTTP.
- Focused green run after implementation: **27 passed** for backup/restore and
  delivery contracts; web: **3 files, 30 tests passed**. The final full acceptance
  run below includes the later Compose-smoke and CI blocking assertions.

### Exact verification evidence

Commands ran from this task worktree using the existing API virtual environment and
project-local `COREPACK_HOME` with `corepack pnpm@10.15.1`.

| Check | Result |
|---|---|
| `services/api/.venv/bin/ruff check services/api tests scripts` | PASS, All checks passed |
| `services/api/.venv/bin/mypy services/api/src` | PASS, no issues in 15 source files |
| `services/api/.venv/bin/pytest -q` | PASS, 128 passed, 1 skipped in final fresh run (33.03s) |
| `services/api/.venv/bin/pytest tests/acceptance -q` | PASS, 30 passed, 1 skipped in 4.80s |
| `services/api/.venv/bin/pytest tests/contracts -q` | PASS, 8 passed |
| `corepack pnpm@10.15.1 lint` | PASS |
| `corepack pnpm@10.15.1 typecheck` | PASS |
| `corepack pnpm@10.15.1 test` | PASS, 3 files / 31 tests |
| `corepack pnpm@10.15.1 build` | PASS, Next.js 16.3.4 compiled, typechecked and generated all routes |
| `for script in scripts/*.sh; do bash -n "$script"; done` | PASS for every script, including the new wrapper |
| Python YAML parse plus permissions/promotion dependency assertions | PASS, workflow YAML and promotion dependency graph valid |
| `node --check apps/web/e2e/foundation.mjs` | PASS |
| `playwright test --list` | PASS, six browser tests discovered |
| `git diff --check` | PASS before report update; rerun after report and immediately before commit |

### Cannot Verify in this executor

- Docker/Compose is absent. `bash scripts/compose_smoke.sh` and
  `bash scripts/acceptance_smoke.sh` each failed closed with their explicit
  Docker-required message. Compose config/ps, real image builds, container hardening,
  blocking Trivy scans, and the fake-tested rollback against real named volumes were
  not executed.
- No PostgreSQL listens on `127.0.0.1:5432`. The explicit disposable
  `agentos_test` acceptance attempt produced 1 setup error and 1 skip from connection
  refusal; PostgreSQL migration/timezone/constraint behavior is not newly claimed.
- Chromium is not installed. Playwright discovery succeeded, while
  `playwright install --list` failed because its browser-cache links directory is
  absent. No real browser execution is claimed in this round.
- `shellcheck`, `actionlint`, and `age` executables are absent. Shell syntax and
  executable YAML/security contracts passed, but they do not substitute for those
  tools or for real age encryption/decryption interoperability.
- GitHub Actions, registry/advisory network calls, action-SHA provenance, Cloudflare
  TLS routing, and production promotion/branch-protection behavior were not executed.
  The Plan 1 completion gate therefore remains OPEN.

## Fix round 2 — restore provenance and origin parity (2026-09-13)

Status: ADDRESSED_IN_CODE; runtime promotion gate remains OPEN.

### Root causes and fixes

1. Round 1 inferred freshness from an empty selected PostgreSQL schema and MinIO
   bucket. A reused named volume could contain another database/bucket, so a later
   `down --volumes` could erase pre-existing data. Restore now requires both exact
   `${project}_postgres_data` and `${project}_minio_data` volumes to be absent before
   archive processing and rechecks immediately after interactive confirmation. After
   Compose startup it verifies both project/logical-volume ownership labels and only
   then sets the invocation-owned cleanup guard. Any failure before that proof leaves
   automatic volume deletion disabled. Regression cases model an empty selected
   database/bucket with data elsewhere in each reused volume and prove refusal occurs
   before startup or cleanup. No real destructive restore ran in this executor.
2. Python's RFC-style parser and the browser's WHATWG parser interpreted ambiguous
   authorities differently. A single JSON fixture now drives both Python generator
   and TypeScript validator tests. The common policy normalizes case, one trailing
   slash and default ports; permits HTTP only for exact loopback hosts; and rejects
   backslashes plus non-canonical numeric IPv4 forms (`127.1`, hex/octal variants)
   rather than accepting runtime-dependent normalization.

### RED evidence

- Focused Python run: **3 failed, 9 passed**. Both reused-volume cases showed no
  volume-name inspection; `https://example.com\\evil.com` was accepted and written.
- After correcting the test fixture path (the first browser invocation was a loader
  error, not behavioral evidence), Vitest ran **40 passed, 1 failed**: the browser
  normalized and accepted `http://127.1`.
- Self-review added the numeric-host mutation `https://0x7f000001`; Python then ran
  **11 passed, 1 failed** and Vitest **42 passed, 1 failed**, proving both still
  accepted a WHATWG-ambiguous hexadecimal IPv4 form.

### GREEN and broader verification

| Check | Result |
|---|---|
| Focused reused-volume restore cases | PASS, 2 passed |
| Shared Python public-origin policy fixtures | PASS, 12 passed |
| `pytest tests/acceptance/test_backup_restore.py -q` | PASS, 20 passed |
| `services/api/.venv/bin/ruff check services/api tests scripts` | PASS |
| `services/api/.venv/bin/mypy services/api/src` | PASS, no issues in 15 source files |
| `services/api/.venv/bin/pytest -q` | PASS, 138 passed, 1 skipped in 34.47s |
| `services/api/.venv/bin/pytest tests/acceptance -q` | PASS, 40 passed, 1 skipped in 5.33s |
| `services/api/.venv/bin/pytest tests/contracts -q` | PASS, 8 passed |
| `corepack pnpm@10.15.1 lint` | PASS |
| `corepack pnpm@10.15.1 typecheck` | PASS |
| `corepack pnpm@10.15.1 test` | PASS, 3 files / 43 tests |
| `corepack pnpm@10.15.1 build` | PASS, production build generated all routes |
| Shell syntax, workflow YAML/blocking graph, Node syntax | PASS |
| `playwright test --list` | PASS, 6 tests discovered |
| `git diff --check` | PASS before report update; rerun immediately before commit |

### Concerns / Cannot Verify

- Docker/Compose remains absent, so real named-volume label behavior, automatic
  rollback, image builds/scans, live PostgreSQL and full Compose acceptance were not
  executed. The tests use deterministic boundary fakes and never mutate real volumes.
- Chromium, `age`, `shellcheck`, and `actionlint` remain unavailable; real browser,
  encryption interoperability and those external-tool checks are not newly claimed.
- The Plan 1 production completion gate remains OPEN pending CI/Ubuntu rehearsal.

## Fix round 3 — atomic restore ownership and narrow origin grammar (2026-09-13)

Status: ADDRESSED_IN_CODE; runtime promotion gate remains OPEN.

### Root causes and fixes

1. Round 2 separated the absence observation from Compose volume creation and then
   trusted standard Compose labels. Two restores could both observe absence; those
   labels identify a project, not the creating invocation. Restore now atomically
   calls `docker volume create` with the expected Compose labels and a nonce derived
   from this invocation's private `mktemp` directory, then immediately verifies all
   three labels. Docker returns an existing same-name volume without replacing its
   labels, so a concurrent winner fails nonce verification before Compose startup.
   Each volume is tracked only after exact verification. Failure cleanup stops
   containers without `--volumes`, re-verifies the nonce separately on every tracked
   volume, and invokes `docker volume rm` only for an exact match. The deterministic
   TOCTOU fake makes PostgreSQL creation belong to this invocation and MinIO creation
   belong to a competitor; the restore refuses startup, deletes only its PostgreSQL
   volume, and never requests deletion of the competitor's volume. No real restore
   or real volume deletion ran in this executor.
2. Python `urlsplit`/IDNA and browser WHATWG parsing canonicalized authorities by
   different rules. Both implementations now use the same deliberately narrow raw
   grammar and manual algorithm: ASCII DNS labels or canonical dotted-quad IPv4,
   exact `[::1]` IPv6 loopback, lowercase scheme/host, optional one trailing slash,
   ports 1–65535, default-port removal, and HTTP only on exact loopback. Non-ASCII,
   percent-encoded, backslash, trailing-dot, malformed-label, abbreviated/numeric
   and non-loopback HTTP authorities are rejected before runtime URL parsing. The
   single shared JSON fixture covers all reported divergences and adjacent mutations.

### RED evidence

- `services/api/.venv/bin/pytest tests/acceptance/test_backup_restore.py::test_restore_toctou_race_removes_only_nonce_owned_volume tests/acceptance/test_delivery_contracts.py::test_environment_generation_matches_shared_public_origin_policy -q`
  failed **7 tests, with 16 passing**. The TOCTOU case observed zero atomic volume
  creates; Python incorrectly accepted trailing-dot, non-ASCII, percent-encoded and
  malformed-label authorities.
- `COREPACK_HOME="$PWD/.corepack" corepack pnpm@10.15.1 --filter @agentos/web test -- --runInBand`
  failed **8 tests, with 45 passing**. Web accepted both reported trailing-dot cases,
  the non-ASCII and percent-encoded authorities, and all four adjacent malformed
  authorities in the new shared fixture.

### GREEN and broader verification

| Check | Result |
|---|---|
| Focused restore race + Python shared-origin command | PASS, 23 passed |
| Focused web/shared-origin suite | PASS, 3 files / 53 tests |
| `services/api/.venv/bin/pytest tests/acceptance/test_backup_restore.py -q` | PASS, 21 passed |
| `services/api/.venv/bin/ruff check services/api tests scripts` | PASS, All checks passed |
| `services/api/.venv/bin/mypy services/api/src` | PASS, no issues in 15 source files |
| `services/api/.venv/bin/pytest -q` | PASS, 149 passed, 1 skipped in 30.58s |
| `services/api/.venv/bin/pytest tests/acceptance -q` | PASS, 51 passed, 1 skipped in 5.94s |
| `services/api/.venv/bin/pytest tests/contracts -q` | PASS, 8 passed |
| `corepack pnpm@10.15.1 lint` | PASS |
| `corepack pnpm@10.15.1 typecheck` | PASS |
| `corepack pnpm@10.15.1 test` | PASS, 3 files / 53 tests |
| `corepack pnpm@10.15.1 build` | PASS, Next.js 16.3.4 compiled, typechecked and generated all routes |
| `for script in scripts/*.sh; do bash -n "$script"; done` | PASS |
| Python YAML/full-SHA/least-permissions/blocking-needs assertions | PASS |
| `node --check apps/web/e2e/foundation.mjs` | PASS |
| `playwright test --list` | PASS, 6 tests discovered |
| `git diff --check` | PASS before report update; rerun immediately before commit |

### Self-review and Cannot Verify

- Cleanup ownership is enabled one volume at a time only after the custom nonce,
  project label and logical-volume label all match. Cleanup never uses Compose's
  broad volume deletion and performs a fresh nonce read immediately before each
  exact `docker volume rm`; unreadable or changed ownership fails closed.
- Python and TypeScript use matching ASCII authority regexes, label-length/shape,
  IPv4, port, loopback and normalization branches. Shared cases include
  `https://127.0.0.1.`, `http://127.0.0.1.`, `https://faß.de`,
  `https://%65xample.com`, normal HTTPS/loopback inputs and default ports.
- Docker/Compose, `age`, `shellcheck`, and `actionlint` are unavailable. Real Docker
  atomic-create behavior, Compose adoption of pre-labelled volumes, actual rollback,
  encryption interoperability, image builds/scans, live PostgreSQL and full Compose
  acceptance were not executed. The boundary tests never touch real Docker state.
- Playwright discovery succeeded, but no installed-browser run or GitHub Actions run
  is claimed. The Plan 1 production completion gate remains OPEN.

## Fix round 4 — pre-start restore teardown isolation (2026-09-13)

Status: ADDRESSED_IN_CODE; runtime promotion gate remains OPEN.

### Root cause and fix

The atomic claim cleanup introduced in round 3 correctly tracked the first
nonce-owned volume when a competing restore won the second-volume race, but
`remove_owned_restore_volumes` unconditionally ran project-scoped
`docker compose down --remove-orphans` before its exact per-volume ownership
checks. Consequently, an invocation that never reached Compose startup could stop
or remove a competing invocation's project containers. The previous TOCTOU
regression excluded only `down --volumes`, so it did not detect this side effect.

Restore now tracks whether this invocation actually attempted Compose startup.
The flag is set immediately before `compose up`, ensuring that an `up` command
which partially starts services and then fails still receives project service
teardown. Cleanup skips Compose teardown when volume claiming fails first, while
continuing to re-read the invocation nonce separately for every tracked volume and
remove only exact nonce matches.

### RED evidence

- After strengthening the real restore entrypoint's TOCTOU boundary test to reject
  every ordinary Compose `down` call, the focused regression failed **1 test**.
  The Docker call log contained `compose ... down --remove-orphans` even though it
  contained no `compose up`, directly reproducing the cross-invocation teardown.
- The repository virtualenv's `pytest` launcher initially exited 127 because its
  `bin/python` target is absent. This was an environment/setup error and was not
  counted as RED. Tests were run with the primary Python interpreter, the existing
  virtualenv site-packages, and `services/api/src` on `PYTHONPATH`.

### GREEN and broader verification

| Check | Result |
|---|---|
| Focused TOCTOU + startup/import rollback cases | PASS, 4 passed |
| `pytest tests/acceptance/test_backup_restore.py -q` | PASS, 22 passed |
| `ruff check services/api tests scripts` | PASS, All checks passed |
| `for script in scripts/*.sh; do bash -n "$script"; done` | PASS |
| `pytest tests/acceptance -q` | PASS, 52 passed, 1 skipped in 5.28s |
| `pytest -q` | PASS, 150 passed, 1 skipped in 24.78s |
| `git diff --check` before report update | PASS |

### Self-review and Cannot Verify

- The race regression now fails on any project-wide `down`, not merely
  `down --volumes`, and still proves only the nonce-owned PostgreSQL volume is
  removed. A startup-failure case independently proves the lifecycle flag is set
  before the startup command: startup, database-import and object-import failures
  all stop project services, re-verify both volume nonces and remove exactly two
  owned volumes without Compose volume deletion.
- Docker/Compose remains unavailable, so real concurrent Compose behavior and
  volume deletion were not executed. The regression uses deterministic Docker and
  age boundary fakes and does not touch Docker state. The explicit Compose/browser
  acceptance test remains skipped, and the Plan 1 production completion gate
  remains OPEN pending CI/Ubuntu rehearsal.
