"""One conservative email policy shared by bootstrap and HTTP authentication."""

import re

EMAIL_MAX_LENGTH = 254
_BROWSER_EMAIL = re.compile(
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*",
    re.ASCII | re.IGNORECASE,
)


def normalize_email(value: str) -> str:
    """Return the canonical identity accepted by the browser's email control."""

    if value != value.strip() or len(value) > EMAIL_MAX_LENGTH:
        raise ValueError("A valid email address is required")
    if _BROWSER_EMAIL.fullmatch(value) is None:
        raise ValueError("A valid email address is required")
    return value.lower()
