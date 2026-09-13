#!/usr/bin/env python3
"""Generate a new mode-0600 Compose environment without printing secrets."""

import base64
import os
import re
import secrets
import sys

path, origin = sys.argv[1:]


def canonicalize_origin(value: str) -> str:
    match = re.fullmatch(
        r"(https|http)://(\[[0-9a-f:]+\]|[a-z0-9.-]+)(?::([0-9]{1,5}))?/?",
        value,
        re.ASCII | re.IGNORECASE,
    )
    if not match:
        raise SystemExit(
            "Use one ASCII origin without path, credentials, query or fragment"
        )
    scheme, raw_host, raw_port = match.groups()
    scheme = scheme.lower()
    host = raw_host.lower()
    if host.startswith("["):
        if host != "[::1]":
            raise SystemExit("Only canonical IPv6 loopback [::1] is supported")
    elif re.fullmatch(r"[0-9.]+", host, re.ASCII):
        parts = host.split(".")
        if not (
            len(parts) == 4
            and all(
                part.isascii()
                and part.isdigit()
                and (part == "0" or not part.startswith("0"))
                and int(part) <= 255
                for part in parts
            )
        ):
            raise SystemExit("Use a canonical dotted-quad IPv4 address")
    elif host != "localhost":
        labels = host.split(".")
        if (
            len(labels) < 2
            or len(host) > 253
            or labels[-1].isdigit()
            or any(
                len(label) > 63
                or not re.fullmatch(
                    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label, re.ASCII
                )
                for label in labels
            )
        ):
            raise SystemExit("Use a valid ASCII public-origin hostname")
    if scheme == "http" and host not in {"localhost", "127.0.0.1", "[::1]"}:
        raise SystemExit(
            "HTTPS origin required (HTTP loopback allowed for disposable acceptance)"
        )
    port = int(raw_port) if raw_port is not None else None
    if port is not None and not 1 <= port <= 65535:
        raise SystemExit("Use a valid public-origin port")
    default_port = 443 if scheme == "https" else 80
    canonical = f"{scheme}://{host}"
    if port is not None and port != default_port:
        canonical += f":{port}"
    return canonical


canonical_origin = canonicalize_origin(origin)
password = secrets.token_hex(32)
values = {
    "AGENTOS_POSTGRES_DB": "agentos",
    "AGENTOS_POSTGRES_USER": "agentos",
    "AGENTOS_POSTGRES_PASSWORD": password,
    "AGENTOS_DATABASE_URL": f"postgresql+asyncpg://agentos:{password}@postgres:5432/agentos",
    "AGENTOS_REDIS_URL": "redis://redis:6379/0",
    "AGENTOS_MINIO_ENDPOINT": "http://minio:9000",
    "AGENTOS_MINIO_ACCESS_KEY": "agentos",
    "AGENTOS_MINIO_SECRET_KEY": secrets.token_hex(32),
    "AGENTOS_MINIO_BUCKET": "agentos",
    "AGENTOS_SESSION_PEPPER": secrets.token_hex(32),
    "AGENTOS_AUTH_PROXY_SECRET": secrets.token_urlsafe(32),
    "AGENTOS_MASTER_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "AGENTOS_PUBLIC_ORIGIN": canonical_origin,
}
with os.fdopen(
    os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
) as output:
    output.write("".join(f"{key}={value}\n" for key, value in values.items()))
print("Environment created; retain the master key and session pepper securely")
