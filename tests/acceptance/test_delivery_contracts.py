"""Executable security contracts for environment generation and port inspection."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ORIGIN_CASES = json.loads(
    (ROOT / "tests/fixtures/public_origins.json").read_text()
)


def test_environment_generation_private_and_no_overwrite(tmp_path):
    destination = tmp_path / "env"
    command = [
        sys.executable,
        str(ROOT / "scripts/generate_env.py"),
        str(destination),
        "https://agentos.example.com",
    ]
    result = subprocess.run(command, capture_output=True)
    assert result.returncode == 0
    assert destination.stat().st_mode & 0o777 == 0o600
    original = destination.read_bytes()
    assert b"AGENTOS_MASTER_KEY=" in original
    values = dict(line.split(b"=", 1) for line in original.splitlines() if line)
    assert len(values[b"AGENTOS_AUTH_PROXY_SECRET"]) >= 32
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert destination.read_bytes() == original
    assert original not in result.stdout


@pytest.mark.parametrize("case", ORIGIN_CASES, ids=lambda case: case["input"])
def test_environment_generation_matches_shared_public_origin_policy(tmp_path, case):
    destination = tmp_path / "env"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_env.py"),
            str(destination),
            case["input"],
        ],
        capture_output=True,
    )
    if case["canonical"] is None:
        assert result.returncode != 0
        assert not destination.exists()
        return
    assert result.returncode == 0, result.stderr
    values = dict(
        line.split("=", 1) for line in destination.read_text().splitlines() if line
    )
    assert values["AGENTOS_PUBLIC_ORIGIN"] == case["canonical"]


@pytest.mark.parametrize(
    "rows, valid",
    [
        (
            [
                {
                    "Config": {
                        "Labels": {"com.docker.compose.service": "web"}
                    },
                    "HostConfig": {
                        "PortBindings": {
                            "3000/tcp": [
                                {"HostIp": "127.0.0.1", "HostPort": "3300"}
                            ]
                        }
                    },
                },
                {
                    "Config": {
                        "Labels": {"com.docker.compose.service": "api"}
                    },
                    "HostConfig": {"PortBindings": {}},
                },
            ],
            True,
        ),
        (
            [
                {
                    "Config": {
                        "Labels": {"com.docker.compose.service": "web"}
                    },
                    "HostConfig": {
                        "PortBindings": {
                            "3000/tcp": [
                                {"HostIp": "0.0.0.0", "HostPort": "3300"}
                            ]
                        }
                    },
                }
            ],
            False,
        ),
        (
            [
                {
                    "Config": {
                        "Labels": {"com.docker.compose.service": "api"}
                    },
                    "HostConfig": {
                        "PortBindings": {
                            "8000/tcp": [
                                {"HostIp": "127.0.0.1", "HostPort": "8000"}
                            ]
                        }
                    },
                }
            ],
            False,
        ),
        ([], False),
    ],
)
def test_live_port_contract(rows, valid):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_ports.py")],
        input=json.dumps(rows).encode(),
        capture_output=True,
    )
    assert (result.returncode == 0) is valid


def test_acceptance_inspects_authoritative_runtime_port_bindings():
    script = (ROOT / "scripts/acceptance_smoke.sh").read_text()

    assert 'docker inspect "${container_ids[@]}" | python3 scripts/check_ports.py' in script
    assert "ps --format json | python3 scripts/check_ports.py" not in script


def test_ci_has_independent_read_only_pinned_gates():
    workflow = ROOT / ".github/workflows/ci.yml"
    assert workflow.is_file(), "Missing delivery workflow"
    model = yaml.safe_load(workflow.read_text())
    assert model["permissions"] == {"contents": "read"}
    assert set(model["jobs"]) >= {
        "backend",
        "frontend",
        "compose-contracts",
        "dependency-audit",
        "containers",
        "acceptance",
    }
    for job in model["jobs"].values():
        assert "write" not in json.dumps(job.get("permissions", {}))
        assert "continue-on-error" not in job
        for step in job["steps"]:
            assert step.get("continue-on-error") is not True
            if "uses" in step:
                reference = step["uses"].split("@")[-1]
                assert len(reference) == 40 and all(
                    char in "0123456789abcdef" for char in reference
                )

    jobs = model["jobs"]
    assert set(jobs["acceptance"]["needs"]) == set(jobs) - {"acceptance"}
    postgres = jobs["backend"]["services"]["postgres"]
    assert postgres["ports"] == ["5432:5432"]
    assert "--health-cmd" in postgres["options"]
    frontend_commands = json.dumps(jobs["frontend"]["steps"])
    assert "playwright install --with-deps chromium" in frontend_commands
    assert "test:e2e" in frontend_commands
    container_commands = json.dumps(jobs["containers"]["steps"])
    assert "docker build" in container_commands
    assert "--exit-code 1" in container_commands
    acceptance_commands = json.dumps(jobs["acceptance"]["steps"])
    assert "compose_smoke.sh" in acceptance_commands
    assert "acceptance_smoke.sh" in acceptance_commands


def test_container_scan_blocks_fixable_high_and_critical_os_and_library_findings():
    model = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    containers = model["jobs"]["containers"]
    images = containers["strategy"]["matrix"]["include"]
    scan = next(
        step["run"]
        for step in containers["steps"]
        if step.get("name") == "Fail on high or critical image vulnerabilities"
    )
    arguments = shlex.split(scan)

    assert images == [
        {"name": "api", "dockerfile": "services/api/Dockerfile"},
        {"name": "web", "dockerfile": "apps/web/Dockerfile"},
    ]
    assert arguments[arguments.index("--exit-code") + 1] == "1"
    assert arguments[arguments.index("--severity") + 1] == "HIGH,CRITICAL"
    assert arguments[arguments.index("--scanners") + 1] == "vuln"
    assert arguments[arguments.index("--pkg-types") + 1] == "os,library"
    assert "--ignore-unfixed" in arguments
    assert "--ignorefile" not in arguments


def test_smoke_refuses_production_project_before_docker():
    result = subprocess.run(
        ["bash", "scripts/compose_smoke.sh"],
        cwd=ROOT,
        env={**os.environ, "COMPOSE_PROJECT_NAME": "agentos"},
        capture_output=True,
    )
    assert result.returncode != 0
    assert b"disposable" in result.stderr


def test_compose_smoke_discards_inherited_agentos_values(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    observed = tmp_path / "docker-calls"
    docker = fake_bin / "docker"
    docker.write_text(
        f'''#!/bin/sh
printf '%s|%s\n' "${{AGENTOS_PUBLIC_ORIGIN-unset}}" "$*" >> "{observed}"
case "$*" in
  *"compose"*"ps --quiet"*) printf fixture-container;;
  *"inspect --format"*) printf healthy;;
  *"compose"*"exec --no-TTY web"*) printf '{{"status":"alive"}}';;
esac
'''
    )
    docker.chmod(0o700)
    result = subprocess.run(
        ["bash", "scripts/compose_smoke.sh"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "AGENTOS_PUBLIC_ORIGIN": "https://malicious.example",
            "AGENTOS_DATABASE_URL": "postgresql://malicious",
        },
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    entries = observed.read_text().splitlines()
    assert entries
    assert all(entry.startswith("unset|") for entry in entries)
    assert all("--env-file /tmp/agentos-compose-smoke." in entry for entry in entries if "compose" in entry)
