# AgentOS CI remediation report

Date: 2026-09-13
Branch: `feature/agentos-foundation-auth`
Starting commit: `9d3912422e519524eaa35c3e6579f3ac0361c78a`

## Implementation plan

**Goal:** Restore the Ubuntu/Docker CI gates without weakening dependency or
container security policy.

**Architecture:** Protect the security behavior with executable Python and shell
contracts, update only the vulnerable dependency pins and generated locks, make
restore cleanup lifecycle state an explicit function input, harden the existing
runtime stages, and make the Trivy promotion rule explicit about fixability and
package types. Keep Node exactly at 22.16.0 and retain blocking HIGH/CRITICAL
scans for both images.

**Tech stack:** Python 3.12/3.13, pytest, uv, Bash, Dockerfiles, GitHub Actions,
YAML, Node 22.16.0, pnpm 10.15.1.

### Task 1: Security contracts and RED evidence

**Files:**

- Modify: `tests/contracts/test_repository_layout.py`
- Modify: `tests/acceptance/test_delivery_contracts.py`
- Modify: `tests/acceptance/test_backup_restore.py`

- [x] Add exact patched Python dependency/lock contracts.
- [x] Add runtime image hardening contracts for OS upgrades and web package-manager removal.
- [x] Add a semantic Trivy workflow contract covering both matrix images, blocking exit status,
      HIGH/CRITICAL severity, fixable-only handling, vulnerability scanning, and OS/library packages.
- [x] Add an executable shell contract that calls restore cleanup with explicit lifecycle state and
      no caller global.
- [x] Run only the new tests and record expected failures caused by the old contracts.

### Task 2: Dependency remediation

**Files:**

- Modify: `services/api/pyproject.toml`
- Regenerate: `services/api/uv.lock`
- Regenerate: `services/api/requirements.lock`

- [x] Pin FastAPI 0.141.1, cryptography 50.0.1, and pytest 9.1.1.
- [x] Resolve compatible transitive dependencies with uv 0.12.8-compatible lock format.
- [x] Export `requirements.lock` reproducibly from the frozen uv lock.
- [x] Run dependency contracts and backend tests.

### Task 3: Shell lifecycle and lint remediation

**Files:**

- Modify: `scripts/operations_common.sh`
- Modify: `scripts/restore.sh`
- Modify: `scripts/backup.sh`
- Modify: `scripts/acceptance_smoke.sh`

- [x] Accept the compose-started state as a required cleanup function argument.
- [x] Pass the restore lifecycle state at the only call site.
- [x] Add narrow SC2016 annotations only where PostgreSQL variables must expand inside containers.
- [x] Run the executable shell contract, restore acceptance tests, and `bash -n` over every shell script.

### Task 4: Runtime image and scan-policy remediation

**Files:**

- Modify: `services/api/Dockerfile`
- Modify: `apps/web/Dockerfile`
- Modify: `.github/workflows/ci.yml`

- [x] Upgrade installed supported OS packages in both final runtime stages.
- [x] Remove npm, npx, Corepack, and package-manager shims/modules from the web runner only.
- [x] Add Trivy `--ignore-unfixed` while preserving exit code 1 and HIGH/CRITICAL severity.
- [x] Explicitly scan `os,library` vulnerability package types for both matrix images.
- [x] Run the repository and workflow contracts.

### Task 5: Full verification, self-review, and commit

- [x] Run backend Ruff, mypy, and the full pytest suite.
- [x] Run frontend ESLint, TypeScript, Vitest, and production build.
- [x] Run shell syntax checks, Actionlint if locally available, lock reproducibility checks,
      dependency audit if locally available, and `git diff --check`.
- [x] Review the complete diff against every CI requirement and mutation-test each contract mentally.
- [x] Record GREEN evidence and explicit Cannot Verify items in this report.
- [x] Commit the reviewed remediation without pushing.

## Root-cause analysis

1. `cryptography`, FastAPI, and pytest were exact direct pins, so the vulnerable
   versions were faithfully retained in `uv.lock` and the exported requirements.
   FastAPI's old resolution also retained vulnerable Starlette 0.46.2.
2. `remove_owned_restore_volumes` lived in `operations_common.sh` but read
   `compose_start_attempted`, which existed only in `restore.sh`; execution happened
   to work for that caller, while standalone static analysis correctly found an
   undeclared cross-file input. The PostgreSQL command strings deliberately use
   single quotes so credentials expand inside the container, but that intent was
   not locally annotated for ShellCheck.
3. Both final images inherited the package state embedded in their base-image
   snapshots. The web runner additionally retained npm/Corepack and their bundled
   libraries even though the standalone application starts directly with Node.
4. The Trivy gate correctly blocked HIGH/CRITICAL findings but also blocked CVEs
   for which the upstream distribution has no fix. It also left OS/library package
   selection implicit, making the promotion contract less reviewable than the
   stated policy.

## RED evidence

- Command:
  `services/api/.venv/bin/pytest -q tests/contracts/test_repository_layout.py::test_runtime_images_upgrade_base_packages_and_drop_unused_web_package_managers tests/contracts/test_repository_layout.py::test_python_security_dependencies_are_pinned_and_locked_to_patched_releases tests/acceptance/test_delivery_contracts.py::test_container_scan_blocks_fixable_high_and_critical_os_and_library_findings tests/acceptance/test_backup_restore.py::test_restore_cleanup_accepts_lifecycle_state_without_a_caller_global`
- Result: **4 failed in 0.19s**, each for the intended missing behavior:
  no API OS upgrade; old `cryptography==45.0.4`; no explicit Trivy
  `--pkg-types`; and `compose_start_attempted: unbound variable` when the shared
  cleanup function was called with lifecycle state but no caller global.
- Resolver compatibility RED: pytest-asyncio 0.26.0 declares pytest `<9`, so
  uv rejected pytest 9.1.1 as unsatisfiable. A focused plugin pin contract then
  failed on `0.26.0 != 1.4.0` before the compatible direct pin was changed.

## Implemented changes

- Direct pins now use FastAPI 0.141.1, cryptography 50.0.1, pytest 9.1.1,
  and pytest-asyncio 1.4.0; uv resolved Starlette 1.6.0 transitively and both
  `uv.lock` and `requirements.lock` were regenerated.
- Restore cleanup receives `compose_start_attempted` as an explicit argument;
  the three intentional container-side SQL expansions have line-local SC2016
  annotations.
- Final API and web runtime stages upgrade their base OS packages. The web
  runner removes npm, npx, Corepack, and their bundled modules after build.
- The Trivy gate remains blocking at HIGH/CRITICAL and now scans OS and library
  packages while excluding only unfixed findings with `--ignore-unfixed`.
- The web runtime contract was narrowed to reject copying application
  `node_modules` while permitting the explicit package-manager cleanup paths.

## GREEN evidence

- Targeted regression/contracts: `64 passed in 2.02s`.
- Backend Ruff: `All checks passed!`.
- Backend mypy: `Success: no issues found in 16 source files`.
- Backend full pytest: `168 passed, 1 skipped in 26.61s`.
- Frontend ESLint, TypeScript, Vitest (`3 files, 58 tests`), and Next build:
  all exited 0.
- `corepack pnpm@10.15.1 install --frozen-lockfile`: lockfile up to date.
- Every `scripts/*.sh` passed `bash -n`; `git diff --check` passed.
- `uv lock --check --project services/api --offline` passed; a fresh frozen
  export matched `requirements.lock` after ignoring the generated command-path
  header.
- `pnpm audit --audit-level high`: no known vulnerabilities found.

## Self-review

- The Trivy command keeps `--exit-code 1`, `--severity HIGH,CRITICAL`, and
  `--scanners vuln`; no CVE IDs or ignorefile were introduced.
- Compose project/env-file isolation and acceptance prerequisites were left
  intact. The lifecycle argument defaults to zero for defensive standalone
  use, while the restore caller passes its explicit state.
- Changes are limited to the CI contracts, dependency manifests/locks,
  runtime image hardening, shell lint remediation, and this report.

## Remaining Cannot Verify concerns

- Docker, Compose config/build, Trivy execution, ShellCheck, and Actionlint
  were not available in this environment (`docker`, `trivy`, `shellcheck`, and
  `actionlint` were all unavailable). CI must provide the final evidence for
  those gates.

## Chromium E2E selector follow-up (2026-09-13)

- RED: the new static contract
  `test_login_e2e_targets_the_visible_authentication_error_alert` failed against
  the broad `page.getByRole("alert")` locator.
- GREEN: `login.spec.ts` now uses
  `page.getByRole("alert", { name: "Authentication failed", exact: true })`,
  targeting the visible application error while excluding Next's route
  announcer.
- Playwright discovery passed and listed all 6 login tests.
- Frontend ESLint, TypeScript, Vitest (`3 files, 58 tests`), and Next build all
  passed after the selector update.
- Full Playwright execution could not run because Chromium was not installed:
  `/root/.cache/ms-playwright/chromium_headless_shell-1243/.../chrome-headless-shell`
  was missing. This is a local environment limitation; CI installs Chromium.

## Chromium E2E selector follow-up (2026-09-13, second correction)

- RED: the contract was updated to require a strict role-alert text filter and
  failed against the accessible-name locator, which matched no alert in the
  latest Chromium run.
- GREEN: the invalid-TOTP assertion now uses
  `page.getByRole("alert").filter({ hasText: /^Authentication failed$/ })`.
  The exact text regex excludes Next's route announcer and preserves Playwright
  strictness if multiple application alerts contain the same message.
- The selector contract passed (`1 passed`), Playwright discovery passed with
  all 6 login tests listed, and frontend ESLint, TypeScript, Vitest (58 tests),
  and Next production build all passed.
- Full browser execution remains unavailable locally because the Chromium
  executable is not installed; CI's browser-install step is required for live
  E2E evidence.

## MinIO registry availability follow-up (2026-09-13)

- RED: `test_minio_images_use_approved_quay_release_pins` failed because the
  Compose contract referenced Docker Hub (`minio/minio` and `minio/mc`).
- GREEN: both images now use the exact pinned official Quay references:
  `quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z` and
  `quay.io/minio/mc:RELEASE.2025-04-16T18-13-26Z`.
- Compose YAML parsed successfully; the registry contract and existing compose
  security contracts passed (`5 passed`).
- Backend Ruff, mypy, full pytest (`170 passed, 1 skipped`), frontend frozen
  install/lint/typecheck/Vitest (58 tests)/build, Playwright discovery (6
  tests), shell syntax, and `git diff --check` passed.
- Docker/Compose execution and image pulls remain unverified locally because
  Docker is unavailable; CI must provide the runtime pull/build evidence.

## Runtime port inspection follow-up (2026-09-13)

- CI confirmed that the Quay-hosted MinIO images pull and become healthy, but
  the final acceptance gate exposed a portability failure in the Compose `ps`
  JSON port report. A first correction also confirmed that the runner does not
  populate the active binding under Docker inspect `NetworkSettings.Ports`.
- RED: the port contract was changed to an authoritative Docker Engine inspect
  fixture and failed with `Expected only web to publish port 3000` against the
  old Compose-formatter parser.
- GREEN: acceptance now resolves every project container ID and pipes `docker
  inspect` output to `check_ports.py`. The checker reads service labels and the
  stable requested bindings in `HostConfig.PortBindings`, requires the web
  `3000/tcp` binding to have a host port on IPv4 loopback, and rejects every
  other published binding.
- The focused runtime-port tests passed (`5 passed`), Ruff passed, and every
  shell script passed syntax validation. Docker execution remains CI-only in
  this environment.

## Browser origin handoff follow-up (2026-09-13)

- CI confirmed the Docker inspect port contract with `Only the web entry point
  is published`, then failed before navigation because the browser process had
  no `AGENTOS_PUBLIC_ORIGIN` after the intentional environment scrub.
- RED: a new delivery contract required the acceptance script to define one
  fixed localhost origin and pass only that value to the browser process.
- GREEN: environment generation and browser navigation now share the local
  `acceptance_origin=http://localhost:3300` variable. The non-secret value is
  scoped to the Node invocation; no credential file is sourced or exported.
