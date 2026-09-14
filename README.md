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

## Run on Windows 11 with WSL2

AgentOS uses Bash-based operational scripts. On Windows, run it inside Ubuntu
24.04 on WSL2 with Docker Desktop's WSL integration. Keep the repository in the
Linux filesystem (for example `~/agentOS`), not under `/mnt/c`, for better file
permissions and performance.

### 1. Install WSL2 and Ubuntu

Open PowerShell as Administrator:

```powershell
wsl --install -d Ubuntu-24.04
wsl --update
wsl --set-default-version 2
```

Restart Windows when prompted, open Ubuntu, and finish creating your Linux user.
Verify the installation from PowerShell:

```powershell
wsl --status
wsl -l -v
```

The Ubuntu distribution must show version `2`.

### 2. Install and connect Docker Desktop

Install Docker Desktop for Windows. In Docker Desktop, enable **Use the WSL 2
based engine**, then enable integration for **Ubuntu-24.04** under **Settings >
Resources > WSL Integration**. Open Ubuntu and verify:

```bash
docker version
docker compose version
```

### 3. Clone AgentOS inside Ubuntu

Run all remaining commands in the Ubuntu terminal:

```bash
sudo apt update
sudo apt install -y git python3 age
cd ~
git clone https://github.com/kevinxcode/agentOS.git
cd agentOS
git checkout main
```

### 4. Generate protected local configuration

The configuration stays outside the repository and is created with restricted
permissions. The generator refuses to overwrite an existing file.

```bash
mkdir -p "$HOME/.config/agentos"
chmod 700 "$HOME/.config/agentos"
python3 scripts/generate_env.py "$HOME/.config/agentos/windows.env" http://localhost:3000
stat -c '%a %n' "$HOME/.config/agentos/windows.env"
```

Create a shell helper for the current terminal session:

```bash
dc() {
  "$PWD/scripts/agentos-compose.sh" \
    agentos-windows \
    "$HOME/.config/agentos/windows.env" \
    "$@"
}
```

### 5. Build, migrate, and start

```bash
dc config --quiet
dc build --pull
dc up -d --wait postgres redis minio
dc run --rm -T minio-init
dc run --rm --no-deps -T api alembic -c /app/alembic.ini upgrade head
dc run --rm --no-deps api python /app/scripts/bootstrap_admin.py --email admin@example.com
dc up -d --wait
```

The bootstrap command asks for the administrator password without displaying it.
Open [http://localhost:3000](http://localhost:3000), sign in, enroll TOTP, and
store the one-time recovery codes securely.

### 6. Check, stop, and restart

```bash
dc ps
dc exec -T api python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/ready").read().decode())'
dc logs --tail 100 web api
```

Stop or start the stack later from the repository directory after recreating the
`dc` helper above:

```bash
dc down
dc up -d --wait
```

Do not run `dc down -v`; `-v` deletes persistent database and object-storage
volumes. For production HTTPS, backups, upgrades, and recovery, follow the Ubuntu
runbooks linked above.

### WSL2 virtualization troubleshooting

If Docker Desktop reports that virtualization is unavailable, enable CPU
virtualization in the BIOS/UEFI (Intel Virtualization Technology/VT-x on the ASUS
ROG Strix SCAR 18), then run in Administrator PowerShell:

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
bcdedit /set hypervisorlaunchtype auto
```

Restart Windows, then run:

```powershell
wsl --update
wsl --shutdown
wsl -l -v
```

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
