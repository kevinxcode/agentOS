import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).parents[2]


def test_required_workspace_files_exist() -> None:
    required = [
        "package.json",
        "pnpm-workspace.yaml",
        "apps/web/package.json",
        "services/api/pyproject.toml",
        "services/api/requirements.lock",
        "services/api/uv.lock",
        "pnpm-lock.yaml",
        "pytest.ini",
        ".env.example",
    ]
    assert [name for name in required if not (ROOT / name).is_file()] == []


def test_secrets_are_not_present_in_env_example() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "change-me" not in text
    assert "sk-" not in text


def test_workspace_tooling_is_pinned() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert package["packageManager"] == "pnpm@10.15.1"
    assert package["scripts"] == {
        "lint": "corepack pnpm@10.15.1 --filter @agentos/web lint",
        "typecheck": "corepack pnpm@10.15.1 --filter @agentos/web typecheck",
        "test": "corepack pnpm@10.15.1 --filter @agentos/web test",
        "build": "corepack pnpm@10.15.1 --filter @agentos/web build",
    }
    assert (ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8") == 'packages: ["apps/*"]\n'
    assert 'PNPM = COREPACK_HOME="$(CURDIR)/.corepack" corepack pnpm@10.15.1' in makefile
    assert "corepack enable" not in makefile
    assert all(not line.lstrip().startswith("pnpm ") for line in makefile.splitlines())


def test_web_image_uses_pinned_toolchain_and_standalone_runtime() -> None:
    dockerfile = (ROOT / "apps/web/Dockerfile").read_text(encoding="utf-8")
    assert "node:22.16.0-" in dockerfile
    assert "corepack pnpm@10.15.1 install --frozen-lockfile" in dockerfile
    assert "corepack pnpm@10.15.1 --filter @agentos/web build" in dockerfile
    assert "corepack enable" not in dockerfile
    assert "corepack prepare" not in dockerfile
    runner = dockerfile.split(" AS runner", maxsplit=1)[1]
    assert "COPY --from=builder" in runner
    # The runner removes npm/corepack's bundled node_modules, but must not copy
    # the application's full dependency tree into the production image.
    assert "COPY --from=builder --chown=node:node /app/node_modules" not in runner
    assert "/.next/standalone" in runner
    assert "/app/apps/web/.next/static ./apps/web/.next/static" in runner
    assert 'CMD ["node", "apps/web/server.js"]' in runner


def test_runtime_images_upgrade_base_packages_and_drop_unused_web_package_managers() -> None:
    api = (ROOT / "services/api/Dockerfile").read_text(encoding="utf-8")
    web = (ROOT / "apps/web/Dockerfile").read_text(encoding="utf-8")
    runner = web.split(" AS runner", maxsplit=1)[1]

    assert "apt-get update" in api
    assert "apt-get upgrade" in api
    assert "rm -rf /var/lib/apt/lists/*" in api
    assert "apk upgrade --no-cache" in runner
    for path in (
        "/usr/local/lib/node_modules/npm",
        "/usr/local/lib/node_modules/corepack",
        "/usr/local/bin/npm",
        "/usr/local/bin/npx",
        "/usr/local/bin/corepack",
    ):
        assert path in runner


def test_web_dependencies_are_pinned_to_the_patched_runtime() -> None:
    package = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))

    assert package["dependencies"] == {
        "next": "16.3.4",
        "react": "19.2.8",
        "react-dom": "19.2.8",
    }
    assert package["devDependencies"]["eslint-config-next"] == "16.3.4"
    assert all(
        not version.startswith(("^", "~", ">", "<", "*"))
        for version in [*package["dependencies"].values(), *package["devDependencies"].values()]
    )


def test_login_e2e_targets_the_visible_authentication_error_alert() -> None:
    e2e = (ROOT / "apps/web/e2e/login.spec.ts").read_text(encoding="utf-8")

    assert 'page.getByRole("alert", { name: "Authentication failed", exact: true })' in e2e
    assert 'page.getByRole("alert")).toHaveText("Authentication failed")' not in e2e


def test_python_dependencies_and_build_backend_are_exactly_pinned() -> None:
    with (ROOT / "services/api/pyproject.toml").open("rb") as file:
        pyproject = tomllib.load(file)

    assert pyproject["build-system"]["requires"] == ["setuptools==80.9.0"]
    dependencies = pyproject["project"]["dependencies"]
    dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]
    assert all("==" in dependency for dependency in [*dependencies, *dev_dependencies])


def test_python_security_dependencies_are_pinned_and_locked_to_patched_releases() -> None:
    with (ROOT / "services/api/pyproject.toml").open("rb") as file:
        pyproject = tomllib.load(file)

    direct = dict(
        dependency.rsplit("==", maxsplit=1)
        for dependency in pyproject["project"]["dependencies"]
    )
    dev = dict(
        dependency.rsplit("==", maxsplit=1)
        for dependency in pyproject["project"]["optional-dependencies"]["dev"]
    )
    locked = dict(
        line.split("==", maxsplit=1)
        for line in (ROOT / "services/api/requirements.lock").read_text().splitlines()
        if line and not line[0].isspace() and "==" in line
    )

    assert direct["cryptography"] == "50.0.1"
    assert direct["fastapi"] == "0.141.1"
    assert dev["pytest"] == "9.1.1"
    assert locked["cryptography"] == "50.0.1"
    assert locked["fastapi"] == "0.141.1"
    assert locked["pytest"] == "9.1.1"
    assert locked["starlette"] == "1.6.0"


def test_async_test_plugin_is_pinned_to_a_pytest_nine_compatible_release() -> None:
    with (ROOT / "services/api/pyproject.toml").open("rb") as file:
        pyproject = tomllib.load(file)

    dev = dict(
        dependency.rsplit("==", maxsplit=1)
        for dependency in pyproject["project"]["optional-dependencies"]["dev"]
    )
    locked = dict(
        line.split("==", maxsplit=1)
        for line in (ROOT / "services/api/requirements.lock").read_text().splitlines()
        if line and not line[0].isspace() and "==" in line
    )

    assert dev["pytest-asyncio"] == "1.4.0"
    assert locked["pytest-asyncio"] == "1.4.0"


def test_environment_template_has_only_empty_required_values() -> None:
    values = dict(
        line.split("=", maxsplit=1)
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line
    )
    assert set(values) == {
        "AGENTOS_DATABASE_URL",
        "AGENTOS_REDIS_URL",
        "AGENTOS_MINIO_ENDPOINT",
        "AGENTOS_MINIO_ACCESS_KEY",
        "AGENTOS_MINIO_SECRET_KEY",
        "AGENTOS_MINIO_BUCKET",
        "AGENTOS_SESSION_PEPPER",
        "AGENTOS_MASTER_KEY",
        "AGENTOS_PUBLIC_ORIGIN",
        "AGENTOS_AUTH_PROXY_SECRET",
    }
    assert all(value == "" for value in values.values())
