"""Exercise shell entrypoints; only Docker transport is replaced by a boundary fake."""

import io
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/backup_archive.py"

SPEC = importlib.util.spec_from_file_location("backup_archive", HELPER)
assert SPEC and SPEC.loader
BACKUP_ARCHIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKUP_ARCHIVE)


def helper(*args):
    return subprocess.run(
        [sys.executable, str(HELPER), *map(str, args)], capture_output=True
    )


def make_restore_archive(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "database.dump").write_bytes(b"PGDMPfixture")
    with tarfile.open(source / "objects.tar", "w") as objects:
        info = tarfile.TarInfo("objects.json")
        info.size = 2
        objects.addfile(info, io.BytesIO(b"[]"))
    archive = tmp_path / "archive.age"
    assert helper("pack", source, archive).returncode == 0
    return archive


def run_restore_with_tty(command, environment, confirmation):
    master, slave = os.openpty()
    try:
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=slave,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        os.close(slave)
        slave = -1
        os.write(master, confirmation.encode())
        stdout, stderr = process.communicate(timeout=10)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        os.close(master)
        if slave >= 0:
            os.close(slave)


def test_archive_roundtrip_and_corruption_rejected_before_extraction(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "database.dump").write_bytes(b"PGDMPfixture")
    with tarfile.open(source / "objects.tar", "w") as archive:
        metadata = b"[]"
        member = tarfile.TarInfo("objects.json")
        member.size = len(metadata)
        archive.addfile(member, io.BytesIO(metadata))
    packed = tmp_path / "backup.tar"
    assert helper("pack", source, packed).returncode == 0
    destination = tmp_path / "validated"
    assert helper("validate", packed, destination).returncode == 0
    assert (destination / "database.dump").read_bytes() == b"PGDMPfixture"
    data = packed.read_bytes().replace(b"PGDMPfixture", b"PGDMPdamaged")
    packed.write_bytes(data)
    failed = tmp_path / "failed"
    assert helper("validate", packed, failed).returncode != 0
    assert not failed.exists()


@pytest.mark.parametrize("name", ["../outside", "/etc/passwd", "database.dump"])
def test_rejects_untrusted_archive_members(tmp_path, name):
    packed = tmp_path / "bad.tar"
    with tarfile.open(packed, "w") as archive:
        member = tarfile.TarInfo(name)
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc/passwd"
        archive.addfile(member)
    target = tmp_path / "validated"
    assert helper("validate", packed, target).returncode != 0
    assert not target.exists()


@pytest.mark.parametrize("script", ["backup.sh", "restore.sh"])
def test_scripts_refuse_missing_arguments(script):
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / script)], capture_output=True
    )
    assert result.returncode == 2
    assert b"Usage:" in result.stderr


def test_restore_refuses_running_app_before_mutation(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls"
    docker = fake_bin / "docker"
    docker.write_text(
        f'#!/bin/sh\necho "$*" >> "{log}"\ncase "$*" in *"ps --services --status running"*) echo web;; *) exit 91;; esac\n'
    )
    docker.chmod(0o700)
    archive = tmp_path / "backup.age"
    archive.write_text("encrypted")
    identity = tmp_path / "key"
    identity.write_text("key")
    envfile = tmp_path / "env"
    envfile.write_text("# test")
    envfile.chmod(0o600)
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/restore.sh"),
            str(archive),
            str(identity),
            "agentos-rehearsal",
            str(envfile),
        ],
        env=environment,
        input=b"RESTORE agentos-rehearsal\n",
        capture_output=True,
    )
    assert result.returncode != 0
    assert b"running" in result.stderr
    assert len(log.read_text().splitlines()) == 1


@pytest.mark.parametrize("kind", ["decryption", "checksum", "confirmation"])
def test_restore_failure_never_mutates_target(tmp_path, kind):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls"
    docker = fake_bin / "docker"
    docker.write_text(
        f'#!/bin/sh\necho "$*" >> "{log}"\ncase "$*" in *"ps --services --status running"*|*"volume ls --quiet --filter name="*) exit 0;; *) exit 91;; esac\n'
    )
    docker.chmod(0o700)
    age = fake_bin / "age"
    # Boundary-only fake: actual age interoperability remains a host/CI gate.
    age.write_text('#!/bin/bash\n[[ $AGE_FAIL != 1 ]] || exit 17\ncp -- "$6" "$5"\n')
    age.chmod(0o700)
    identity = tmp_path / "key"
    identity.write_text("private-key-fixture")
    identity.chmod(0o600)
    envfile = tmp_path / "env"
    envfile.write_text("# fixture")
    envfile.chmod(0o600)
    source = tmp_path / "source"
    source.mkdir()
    (source / "database.dump").write_bytes(b"PGDMPfixture")
    with tarfile.open(source / "objects.tar", "w") as objects:
        info = tarfile.TarInfo("objects.json")
        info.size = 2
        objects.addfile(info, io.BytesIO(b"[]"))
    archive = tmp_path / "archive.age"
    assert helper("pack", source, archive).returncode == 0
    if kind == "checksum":
        archive.write_bytes(
            archive.read_bytes().replace(b"PGDMPfixture", b"PGDMPdamaged")
        )
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "AGE_FAIL": "1" if kind == "decryption" else "0",
    }
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/restore.sh"),
            str(archive),
            str(identity),
            "agentos-rehearsal",
            str(envfile),
        ],
        env=environment,
        input=b"RESTORE agentos-rehearsal\n",
        capture_output=True,
    )
    assert result.returncode != 0
    entries = log.read_text().splitlines()
    assert len(entries) == 3
    assert not any(" up " in entry or "down --volumes" in entry for entry in entries)
    if kind == "confirmation":
        assert b"interactive terminal" in result.stderr
    elif kind == "checksum":
        assert b"archive operation failed" in result.stderr


def test_environment_file_cannot_be_overridden_by_inherited_credentials(tmp_path):
    envfile = tmp_path / "env"
    envfile.write_text("# exact target")
    envfile.chmod(0o600)
    command = f'source "{ROOT}/scripts/operations_common.sh"; configure_target agentos-rehearsal "$1"; [[ -z ${{AGENTOS_DATABASE_URL+x}} ]]'
    result = subprocess.run(
        ["bash", "-c", command, "test", str(envfile)],
        env={**os.environ, "AGENTOS_DATABASE_URL": "production-override"},
        capture_output=True,
    )
    assert result.returncode == 0


def test_malformed_object_metadata_is_rejected_before_extraction(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "database.dump").write_bytes(b"PGDMPfixture")
    # Valid checksums but a missing content type must not fail halfway through import.
    records = [{"key": "safe-object", "sha256": hashlib.sha256(b"body").hexdigest()}]
    with tarfile.open(source / "objects.tar", "w") as objects:
        for name, payload in [
            ("data/0", b"body"),
            ("objects.json", json.dumps(records).encode()),
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            objects.addfile(member, io.BytesIO(payload))
    archive = tmp_path / "backup.tar"
    assert helper("pack", source, archive).returncode == 0
    assert helper("validate", archive, tmp_path / "target").returncode != 0
    assert not (tmp_path / "target").exists()


def test_object_target_preflight_refuses_a_nonempty_bucket(monkeypatch):
    class ObjectStore:
        def list_objects_v2(self, **_kwargs):
            return {"KeyCount": 1}

    monkeypatch.setenv("AGENTOS_MINIO_BUCKET", "agentos")
    monkeypatch.setattr(BACKUP_ARCHIVE, "client", lambda: ObjectStore())
    with pytest.raises(ValueError, match="empty"):
        BACKUP_ARCHIVE.check_empty_objects()


def test_backup_pipeline_exports_validates_and_publishes_without_overwrite(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    object_source = tmp_path / "objects.tar"
    with tarfile.open(object_source, "w") as archive:
        info = tarfile.TarInfo("objects.json")
        info.size = 2
        archive.addfile(info, io.BytesIO(b"[]"))
    docker = fake_bin / "docker"
    docker.write_text(f"""#!/bin/sh
case "$*" in
  *"ps --services --status running"*) exit 0;;
  *"pg_dump"*"--format=custom --no-owner --no-acl"*) printf PGDMPfixture;;
  *"python /app/scripts/backup_archive.py export"*) cat "{object_source}";;
  *) exit 91;;
esac
""")
    docker.chmod(0o700)
    age = fake_bin / "age"
    # Deliberately not cryptography: enforce age boundary flags, then capture payload.
    age.write_text("""#!/bin/sh
[ "$1" = --recipient ] && [ "$2" = age1fixture ] && [ "$3" = --output ] || exit 92
cp -- "$5" "$4"
""")
    age.chmod(0o700)
    envfile = tmp_path / "env"
    envfile.write_text("# fixture")
    envfile.chmod(0o600)
    output = tmp_path / "backups"
    output.mkdir()
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    command = [
        "bash",
        str(ROOT / "scripts/backup.sh"),
        str(output),
        "age1fixture",
        "agentos-rehearsal",
        str(envfile),
    ]
    for _ in range(2):
        result = subprocess.run(command, env=environment, capture_output=True)
        assert result.returncode == 0, result.stderr
    archives = list(output.iterdir())
    assert len(archives) == 2
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in archives)
    assert helper("validate", archives[0], tmp_path / "validated").returncode == 0
    assert (tmp_path / "validated/database.dump").read_bytes() == b"PGDMPfixture"


def test_operator_compose_uses_only_protected_env_file_values(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    observed = tmp_path / "observed"
    docker = fake_bin / "docker"
    docker.write_text(
        f'''#!/bin/sh
printf '%s\n' "${{AGENTOS_DATABASE_URL-unset}}|${{COMPOSE_FILE-unset}}|$*" > "{observed}"
'''
    )
    docker.chmod(0o700)
    envfile = tmp_path / "production.env"
    envfile.write_text("AGENTOS_DATABASE_URL=protected-value\n")
    envfile.chmod(0o600)
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/agentos-compose.sh"),
            "agentos",
            str(envfile),
            "config",
            "--quiet",
        ],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "AGENTOS_DATABASE_URL": "malicious-inherited-value",
            "COMPOSE_FILE": "/tmp/malicious-compose.yaml",
        },
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    value, compose_file, arguments = observed.read_text().strip().split("|", 2)
    assert value == "unset"
    assert compose_file == "unset"
    assert arguments == (
        f"compose --project-name agentos --env-file {envfile} "
        f"-f {ROOT / 'compose.yaml'} config --quiet"
    )


@pytest.mark.parametrize(
    ("existing_volume", "hidden_data"),
    [
        ("postgres_data", "another database in the reused PostgreSQL volume"),
        ("minio_data", "another bucket in the reused MinIO volume"),
    ],
)
def test_restore_refuses_reused_volume_before_start_or_cleanup(
    tmp_path, existing_volume, hidden_data
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "docker-calls"
    project = "agentos-rehearsal-reused"
    full_volume = f"{project}_{existing_volume}"
    docker = fake_bin / "docker"
    docker.write_text(
        f'''#!/bin/sh
printf '%s\n' "$*" >> "{calls}"
case "$*" in
  *"volume ls --quiet --filter name=^{full_volume}$"*) printf '%s\n' "{full_volume}";;
  *"volume ls --quiet --filter name="*) exit 0;;
  *"ps --services --status running"*) exit 0;;
  *"up -d --wait postgres minio redis"*|*"run --rm -T minio-init"*) exit 0;;
  *"SELECT count(*) FROM information_schema.tables"*) printf 0; exit 0;;
  *"backup_archive.py check-empty"*) exit 0;;
  *"pg_restore"*) cat >/dev/null; exit 97;;
  *"down --volumes --remove-orphans"*) exit 0;;
  *) exit 95;;
esac
'''
    )
    docker.chmod(0o700)
    age = fake_bin / "age"
    age.write_text('#!/bin/sh\ncp -- "$6" "$5"\n')
    age.chmod(0o700)
    archive = make_restore_archive(tmp_path)
    identity = tmp_path / "identity"
    identity.write_text("AGE-SECRET-KEY-fixture")
    identity.chmod(0o600)
    envfile = tmp_path / "rehearsal.env"
    envfile.write_text("# selected database and bucket appear empty\n")
    envfile.chmod(0o600)

    result = run_restore_with_tty(
        [
            "bash",
            str(ROOT / "scripts/restore.sh"),
            str(archive),
            str(identity),
            project,
            str(envfile),
        ],
        {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        f"RESTORE {project}\n",
    )

    assert result.returncode != 0, hidden_data
    entries = calls.read_text().splitlines()
    assert any(full_volume in entry for entry in entries)
    assert not any(" up " in entry for entry in entries)
    assert not any("down --volumes" in entry for entry in entries)
    assert b"already exists" in result.stderr


def test_restore_toctou_race_removes_only_nonce_owned_volume(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "docker-calls"
    nonce = tmp_path / "restore-nonce"
    project = "agentos-rehearsal-race"
    postgres_volume = f"{project}_postgres_data"
    minio_volume = f"{project}_minio_data"
    docker = fake_bin / "docker"
    docker.write_text(
        f'''#!/bin/bash
printf '%s\n' "$*" >> "{calls}"
case "$*" in
  *"ps --services --status running"*|*"volume ls --quiet --filter name="*) exit 0;;
  *"volume create"*"{postgres_volume}")
    for argument in "$@"; do
      case "$argument" in agentos.restore.nonce=*) printf '%s' "${{argument#*=}}" > "{nonce}";; esac
    done
    printf '%s\n' "{postgres_volume}"
    ;;
  *"volume create"*"{minio_volume}") printf '%s\n' "{minio_volume}";;
  *"volume inspect --format"*"com.docker.compose.project"*"{postgres_volume}")
    printf '%s|{project}|postgres_data' "$(cat "{nonce}" 2>/dev/null)"
    ;;
  *"volume inspect --format"*"com.docker.compose.project"*"{minio_volume}")
    printf 'competing-invocation|{project}|minio_data'
    ;;
  *"volume inspect --format"*"{postgres_volume}") cat "{nonce}";;
  *"volume rm"*"{postgres_volume}") exit 0;;
  *) exit 93;;
esac
'''
    )
    docker.chmod(0o700)
    age = fake_bin / "age"
    age.write_text('#!/bin/sh\ncp -- "$6" "$5"\n')
    age.chmod(0o700)
    archive = make_restore_archive(tmp_path)
    identity = tmp_path / "identity"
    identity.write_text("AGE-SECRET-KEY-fixture")
    identity.chmod(0o600)
    envfile = tmp_path / "rehearsal.env"
    envfile.write_text("# selected target\n")
    envfile.chmod(0o600)

    result = run_restore_with_tty(
        [
            "bash",
            str(ROOT / "scripts/restore.sh"),
            str(archive),
            str(identity),
            project,
            str(envfile),
        ],
        {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        f"RESTORE {project}\n",
    )

    assert result.returncode != 0
    entries = calls.read_text().splitlines()
    assert sum("volume create" in entry for entry in entries) == 2
    assert any("agentos.restore.nonce=" in entry for entry in entries)
    assert any("volume rm" in entry and postgres_volume in entry for entry in entries)
    assert not any("volume rm" in entry and minio_volume in entry for entry in entries)
    assert not any(" up " in entry for entry in entries)
    assert not any(" down " in entry for entry in entries)
    assert b"not owned by this restore invocation" in result.stderr


@pytest.mark.parametrize("failure", ["startup", "database", "objects"])
def test_confirmed_restore_rolls_back_fresh_target_after_startup_or_import_failure(
    tmp_path, failure
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "docker-calls"
    nonce = tmp_path / "restore-nonce"
    docker = fake_bin / "docker"
    docker.write_text(
        f'''#!/bin/bash
printf '%s|%s\n' "${{AGENTOS_DATABASE_URL-unset}}" "$*" >> "{calls}"
case "$*" in
  *"ps --services --status running"*) exit 0;;
  *"volume ls --quiet --filter name="*) exit 0;;
  *"volume create"*)
    for argument in "$@"; do
      case "$argument" in agentos.restore.nonce=*) printf '%s' "${{argument#*=}}" > "{nonce}";; esac
    done
    exit 0
    ;;
  *"volume inspect --format"*"com.docker.compose.project"*"_postgres_data"*) printf '%s|agentos-rehearsal-exact|postgres_data' "$(cat "{nonce}")";;
  *"volume inspect --format"*"com.docker.compose.project"*"_minio_data"*) printf '%s|agentos-rehearsal-exact|minio_data' "$(cat "{nonce}")";;
  *"volume inspect --format"*"_postgres_data"*|*"volume inspect --format"*"_minio_data"*) cat "{nonce}";;
  *"volume rm"*) exit 0;;
  *"SELECT count(*) FROM information_schema.tables"*) printf 0; exit 0;;
  *"backup_archive.py check-empty"*) exit 0;;
  *"pg_restore"*) cat >/dev/null; [[ "{failure}" != database ]];;
  *"backup_archive.py import"*) [[ "{failure}" != objects ]];;
  *"down --remove-orphans"*) exit 0;;
  *"up -d --wait postgres minio redis"*) [[ "{failure}" != startup ]];;
  *"run --rm -T minio-init"*) exit 0;;
  *) exit 93;;
esac
'''
    )
    docker.chmod(0o700)
    age = fake_bin / "age"
    age.write_text('#!/bin/sh\ncp -- "$6" "$5"\n')
    age.chmod(0o700)
    archive = make_restore_archive(tmp_path)
    identity = tmp_path / "identity"
    identity.write_text("AGE-SECRET-KEY-fixture")
    identity.chmod(0o600)
    envfile = tmp_path / "rehearsal.env"
    envfile.write_text("AGENTOS_DATABASE_URL=protected-target\n")
    envfile.chmod(0o600)
    command = [
        "bash",
        str(ROOT / "scripts/restore.sh"),
        str(archive),
        str(identity),
        "agentos-rehearsal-exact",
        str(envfile),
    ]
    result = run_restore_with_tty(
        command,
        {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "AGENTOS_DATABASE_URL": "malicious-inherited-value",
        },
        "RESTORE agentos-rehearsal-exact\n",
    )
    assert result.returncode != 0
    entries = calls.read_text().splitlines()
    assert all(entry.startswith("unset|") for entry in entries)
    compose_entries = [entry for entry in entries if "|compose " in entry]
    assert all(
        "--project-name agentos-rehearsal-exact" in entry for entry in compose_entries
    )
    assert all(f"--env-file {envfile}" in entry for entry in compose_entries)
    assert sum("volume create" in entry for entry in entries) == 2
    assert sum("volume inspect --format" in entry for entry in entries) == 4
    database_indexes = [i for i, entry in enumerate(entries) if "pg_restore" in entry]
    object_indexes = [
        i for i, entry in enumerate(entries) if "backup_archive.py import" in entry
    ]
    if failure == "startup":
        assert database_indexes == []
        assert object_indexes == []
    elif failure == "database":
        assert len(database_indexes) == 1
        assert object_indexes == []
    else:
        assert database_indexes[0] < object_indexes[0]
    assert any(entry.endswith("down --remove-orphans") for entry in entries)
    assert sum("volume rm" in entry for entry in entries) == 2
    assert not any("down --volumes" in entry for entry in entries)
    assert not any(
        " up " in entry and (" api" in entry or " web" in entry)
        for entry in entries
    )


def test_confirmed_restore_rehearsal_imports_database_then_objects_without_activation(
    tmp_path,
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "docker-calls"
    nonce = tmp_path / "restore-nonce"
    docker = fake_bin / "docker"
    docker.write_text(
        f'''#!/bin/sh
printf '%s\n' "$*" >> "{calls}"
case "$*" in
  *"ps --services --status running"*) exit 0;;
  *"volume ls --quiet --filter name="*) exit 0;;
  *"volume create"*)
    for argument in "$@"; do
      case "$argument" in agentos.restore.nonce=*) printf '%s' "${{argument#*=}}" > "{nonce}";; esac
    done
    exit 0
    ;;
  *"volume inspect --format"*"com.docker.compose.project"*"_postgres_data"*) printf '%s|agentos-rehearsal-success|postgres_data' "$(cat "{nonce}")";;
  *"volume inspect --format"*"com.docker.compose.project"*"_minio_data"*) printf '%s|agentos-rehearsal-success|minio_data' "$(cat "{nonce}")";;
  *"SELECT count(*) FROM information_schema.tables"*) printf 0; exit 0;;
  *"backup_archive.py check-empty"*) exit 0;;
  *"pg_restore"*) cat >/dev/null; exit 0;;
  *"backup_archive.py import"*) exit 0;;
  *"up -d --wait postgres minio redis"*|*"run --rm -T minio-init"*) exit 0;;
  *) exit 94;;
esac
'''
    )
    docker.chmod(0o700)
    age = fake_bin / "age"
    age.write_text('#!/bin/sh\ncp -- "$6" "$5"\n')
    age.chmod(0o700)
    archive = make_restore_archive(tmp_path)
    identity = tmp_path / "identity"
    identity.write_text("AGE-SECRET-KEY-fixture")
    identity.chmod(0o600)
    envfile = tmp_path / "rehearsal.env"
    envfile.write_text("AGENTOS_DATABASE_URL=protected-target\n")
    envfile.chmod(0o600)
    result = run_restore_with_tty(
        [
            "bash",
            str(ROOT / "scripts/restore.sh"),
            str(archive),
            str(identity),
            "agentos-rehearsal-success",
            str(envfile),
        ],
        {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        "RESTORE agentos-rehearsal-success\n",
    )
    assert result.returncode == 0, result.stderr
    entries = calls.read_text().splitlines()
    database_index = next(i for i, entry in enumerate(entries) if "pg_restore" in entry)
    object_index = next(
        i for i, entry in enumerate(entries) if "backup_archive.py import" in entry
    )
    assert database_index < object_index
    assert not any("down --volumes" in entry for entry in entries)
    assert not any(
        " up " in entry and (" api" in entry or " web" in entry)
        for entry in entries
    )
    assert b"Restore rehearsal imported successfully" in result.stdout
