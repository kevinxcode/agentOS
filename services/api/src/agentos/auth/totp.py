"""TOTP generation and bounded-window counter matching."""

import hmac
import re
from datetime import datetime

import pyotp


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="AgentOS")


def matching_counter(secret: str, code: str, now: datetime) -> int | None:
    """Accept exactly six ASCII digits within ±1 30-second step."""
    if re.fullmatch(r"[0-9]{6}", code) is None:
        return None
    totp = pyotp.TOTP(secret)
    counter = int(now.timestamp()) // 30
    matches = [
        candidate
        for candidate in (counter - 1, counter, counter + 1)
        if hmac.compare_digest(totp.at(candidate * 30), code)
    ]
    return max(matches) if matches else None
