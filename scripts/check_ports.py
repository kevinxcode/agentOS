#!/usr/bin/env python3
"""Validate authoritative Docker inspect JSON for Compose service bindings."""

import json
import sys

raw = sys.stdin.read().strip()
rows = json.loads(raw)
published = set()
for row in rows:
    service = row.get("Config", {}).get("Labels", {}).get(
        "com.docker.compose.service"
    )
    for target, bindings in row.get("NetworkSettings", {}).get("Ports", {}).items():
        for binding in bindings or []:
            if service != "web" or target != "3000/tcp":
                raise SystemExit("Unexpected public port binding")
            if binding.get("HostIp") != "127.0.0.1":
                raise SystemExit("Web port must bind only to IPv4 loopback")
            if not binding.get("HostPort"):
                raise SystemExit("Web port has no published host port")
            published.add(service)
if published != {"web"}:
    raise SystemExit("Expected only web to publish port 3000")
print("Only the web entry point is published")
