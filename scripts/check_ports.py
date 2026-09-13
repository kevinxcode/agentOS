#!/usr/bin/env python3
"""Validate Docker Compose ps JSON (JSON array or one object per line)."""

import json
import sys

raw = sys.stdin.read().strip()
rows = (
    json.loads(raw)
    if raw.startswith("[")
    else [json.loads(line) for line in raw.splitlines()]
)
published = set()
for row in rows:
    for port in row.get("Publishers") or []:
        if port.get("PublishedPort", 0):
            if row["Service"] != "web" or port["TargetPort"] != 3000:
                raise SystemExit("Unexpected public port binding")
            if port.get("URL") != "127.0.0.1":
                raise SystemExit("Web port must bind only to IPv4 loopback")
            published.add(row["Service"])
if published != {"web"}:
    raise SystemExit("Expected only web to publish port 3000")
print("Only the web entry point is published")
