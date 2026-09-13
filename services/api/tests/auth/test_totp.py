"""Known RFC 6238 seed, with bounded six-digit verifier behavior."""

from datetime import UTC, datetime

import pytest

from agentos.auth.totp import matching_counter

SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.parametrize("timestamp", [30, 59, 60, 89])
def test_rfc_counter_is_accepted_once_within_window(timestamp) -> None:
    # RFC 6238 SHA-1 vector at 59 seconds: 94287082, reduced to six digits.
    assert matching_counter(SEED, "287082", datetime.fromtimestamp(timestamp, UTC)) == 1


@pytest.mark.parametrize("timestamp", [90, 120])
def test_code_outside_window_is_rejected(timestamp) -> None:
    assert matching_counter(SEED, "287082", datetime.fromtimestamp(timestamp, UTC)) is None


@pytest.mark.parametrize("code", ["２８７０８２", "28708", "2870820", " 287082", "bad"])
def test_noncanonical_totp_input_is_rejected(code) -> None:
    assert matching_counter(SEED, code, datetime.fromtimestamp(59, UTC)) is None
