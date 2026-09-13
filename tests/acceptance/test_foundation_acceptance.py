"""Foundation gate: real HTTP/database locally, Compose/browser only when requested."""

import os
import subprocess
from pathlib import Path

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from agentos.auth.models import AuditEvent, RecoveryCode

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_foundation_acceptance(foundation_stack):
    app, database = foundation_stack
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as api:
        assert (await api.get("/auth/me")).status_code == 401
        credentials = {"email": "admin@example.com", "password": "acceptance-password"}
        assert (await api.post("/auth/login", json=credentials)).json() == {
            "next": "totp_enrollment"
        }
        assert (await api.get("/auth/me")).status_code == 401
        enrollment = await api.post("/auth/totp/enroll")
        totp = pyotp.parse_uri(enrollment.json()["otpauth_uri"])
        confirmed = await api.post("/auth/totp/confirm", json={"code": totp.now()})
        codes = confirmed.json()["recovery_codes"]
        assert len(set(codes)) == 10
        assert (await api.get("/auth/me")).status_code == 200
        full = api.cookies.get("agentos_session")
        assert (await api.post("/auth/logout")).status_code == 204
        assert (await api.get("/auth/me")).status_code == 401
        assert (
            await api.get("/auth/me", headers={"Cookie": f"agentos_session={full}"})
        ).status_code == 401
        await api.post("/auth/login", json=credentials)
        assert (
            await api.post("/auth/recovery", json={"code": codes[0]})
        ).status_code == 200
        await api.post("/auth/logout")
        await api.post("/auth/login", json=credentials)
        assert (
            await api.post("/auth/recovery", json={"code": codes[0]})
        ).status_code == 401
    async with database.session_factory() as db:
        stored = (await db.scalars(select(RecoveryCode))).all()
        assert all(row.code_hash.startswith("$argon2id$") for row in stored)
        assert sum(row.used_at is not None for row in stored) == 1
        events = (await db.scalars(select(AuditEvent))).all()
        assert {(row.action, row.outcome) for row in events} >= {
            ("auth.login", "success"),
            ("auth.totp.enrolled", "success"),
            ("auth.logout", "success"),
        }
        assert all(not row.safe_metadata for row in events)


@pytest.mark.skipif(
    os.getenv("AGENTOS_COMPOSE_ACCEPTANCE") != "1",
    reason="Requires explicit disposable Docker/Chromium gate",
)
def test_compose_browser_acceptance():
    subprocess.run(["bash", "scripts/acceptance_smoke.sh"], cwd=ROOT, check=True)
