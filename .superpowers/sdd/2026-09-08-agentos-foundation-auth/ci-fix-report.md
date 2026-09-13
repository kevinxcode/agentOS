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
