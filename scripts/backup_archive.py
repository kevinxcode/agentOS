#!/usr/bin/env python3
"""Versioned backup container; validate all members before writing restored files.

Object keys are JSON values, never local paths. No tar extract/extractall is used.
The MinIO export captures current object bytes and content types, not bucket policy,
versions or IAM configuration. Run with writers stopped for cross-store consistency.
"""

import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def members(archive):
    entries = archive.getmembers()
    if any(not member.isfile() for member in entries):
        raise ValueError("Only regular members are allowed")
    result = {member.name: member for member in entries}
    if len(result) != len(entries):
        raise ValueError("Duplicate archive members")
    return result


def object_manifest(archive):
    entries = members(archive)
    if "objects.json" not in entries or entries["objects.json"].size > 16 * 1024 * 1024:
        raise ValueError("Invalid object manifest")
    records = json.load(archive.extractfile("objects.json"))
    if not isinstance(records, list):
        raise ValueError("Invalid object manifest")
    expected = {"objects.json"}
    keys = set()
    for index, record in enumerate(records):
        name = f"data/{index}"
        if (
            not isinstance(record, dict)
            or set(record) != {"key", "sha256", "content_type"}
            or not isinstance(record["sha256"], str)
            or len(record["sha256"]) != 64
            or not isinstance(record["content_type"], str)
            or not record["content_type"]
            or not record["content_type"].isascii()
            or any(
                ord(char) < 32 or ord(char) == 127 for char in record["content_type"]
            )
        ):
            raise ValueError("Invalid object metadata")
        if (
            not isinstance(record["key"], str)
            or not record["key"]
            or record["key"] in keys
        ):
            raise ValueError("Invalid or duplicate object key")
        if len(record["key"].encode("utf-8")) > 1024:
            raise ValueError("Oversized object key")
        keys.add(record["key"])
        expected.add(name)
        if name not in entries or digest(archive.extractfile(name)) != record["sha256"]:
            raise ValueError("Object checksum mismatch")
    if set(entries) != expected:
        raise ValueError("Unexpected object archive members")
    return records


def pack(source, destination):
    source = Path(source)
    checksums = {}
    for name in ("database.dump", "objects.tar"):
        with (source / name).open("rb") as stream:
            checksums[name] = digest(stream)
    manifest = json.dumps({"version": 1, "sha256": checksums}).encode()
    with tarfile.open(destination, "x") as archive:
        for name in checksums:
            archive.add(source / name, arcname=name, recursive=False)
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest)
        archive.addfile(info, io.BytesIO(manifest))


def validate(source, destination):
    target = Path(destination)
    if target.exists():
        raise ValueError("Validation destination must not exist")
    with tarfile.open(source, "r:") as archive:
        entries = members(archive)
        if set(entries) != {"database.dump", "objects.tar", "manifest.json"}:
            raise ValueError("Unexpected backup members")
        if entries["manifest.json"].size > 4096:
            raise ValueError("Oversized manifest")
        manifest = json.load(archive.extractfile("manifest.json"))
        if manifest["version"] != 1 or set(manifest["sha256"]) != {
            "database.dump",
            "objects.tar",
        }:
            raise ValueError("Unsupported manifest")
        for name, expected in manifest["sha256"].items():
            if digest(archive.extractfile(name)) != expected:
                raise ValueError("Backup checksum mismatch")
        if archive.extractfile("database.dump").read(5) != b"PGDMP":
            raise ValueError("Not a custom-format PostgreSQL dump")
        with tarfile.open(
            fileobj=archive.extractfile("objects.tar"), mode="r:"
        ) as objects:
            object_manifest(objects)
        target.mkdir(mode=0o700)
        for name in ("database.dump", "objects.tar"):
            with (target / name).open("xb") as output:
                shutil.copyfileobj(archive.extractfile(name), output)


def client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ["AGENTOS_MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["AGENTOS_MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["AGENTOS_MINIO_SECRET_KEY"],
    )


def export_objects():
    s3 = client()
    bucket = os.environ["AGENTOS_MINIO_BUCKET"]
    records = []
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for item in page.get("Contents", []):
                obj = s3.get_object(Bucket=bucket, Key=item["Key"])
                # Spool one object privately; keeps memory bounded and allows a checksum.
                import tempfile

                with tempfile.TemporaryFile() as buffer:
                    with obj["Body"] as body:
                        shutil.copyfileobj(body, buffer)
                    buffer.seek(0)
                    checksum = digest(buffer)
                    buffer.seek(0)
                    member = tarfile.TarInfo(f"data/{len(records)}")
                    member.size = obj["ContentLength"]
                    archive.addfile(member, buffer)
                records.append(
                    {
                        "key": item["Key"],
                        "sha256": checksum,
                        "content_type": obj.get(
                            "ContentType", "application/octet-stream"
                        ),
                    }
                )
        data = json.dumps(records).encode()
        member = tarfile.TarInfo("objects.json")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))


def check_empty_objects():
    s3 = client()
    bucket = os.environ["AGENTOS_MINIO_BUCKET"]
    if s3.list_objects_v2(Bucket=bucket, MaxKeys=1).get("KeyCount", 0):
        raise ValueError("Restore bucket must be empty")


def import_objects(source):
    with tarfile.open(source, "r:") as archive:
        records = object_manifest(archive)
        s3 = client()
        bucket = os.environ["AGENTOS_MINIO_BUCKET"]
        # Recheck immediately before upload to close the preflight/import race.
        if s3.list_objects_v2(Bucket=bucket, MaxKeys=1).get("KeyCount", 0):
            raise ValueError("Restore bucket must be empty")
        for index, record in enumerate(records):
            s3.upload_fileobj(
                archive.extractfile(f"data/{index}"),
                bucket,
                record["key"],
                ExtraArgs={"ContentType": record["content_type"]},
            )


def main():
    operation, *args = sys.argv[1:]
    try:
        if operation == "pack":
            pack(*args)
        elif operation == "validate":
            validate(*args)
        elif operation == "export":
            export_objects()
        elif operation == "check-empty":
            check_empty_objects()
        elif operation == "import":
            import_objects(*args)
        else:
            raise ValueError("Unknown archive operation")
    except Exception:
        # SDK/driver exceptions may contain endpoint credentials or object keys.
        print("Backup archive operation failed; no secrets printed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
