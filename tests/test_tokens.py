import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from chemstock.tokens import create_access_token, read_access_token

KEY = "k" * 64
OTHER_KEY = "o" * 64
LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)
LATER = datetime.now(UTC) + timedelta(hours=1)


def test_round_trip() -> None:
    token = create_access_token("42", KEY, timedelta(minutes=5))

    assert read_access_token(token, KEY) == "42"


def test_expired_token_is_rejected() -> None:
    token = create_access_token("42", KEY, timedelta(minutes=5), now=LONG_AGO)

    assert read_access_token(token, KEY) is None


def test_token_signed_with_another_key_is_rejected() -> None:
    token = create_access_token("42", OTHER_KEY, timedelta(minutes=5))

    assert read_access_token(token, KEY) is None


def test_tampered_payload_is_rejected() -> None:
    token = create_access_token("42", KEY, timedelta(minutes=5))
    header, _payload, signature = token.split(".")
    forged = json.dumps({"sub": "1", "exp": 9999999999}).encode()
    forged_part = jwt.utils.base64url_encode(forged).decode()

    assert read_access_token(f"{header}.{forged_part}.{signature}", KEY) is None


def test_unsigned_token_is_rejected() -> None:
    token = jwt.encode({"sub": "42", "exp": LATER}, "", algorithm="none")

    assert read_access_token(token, KEY) is None


def test_token_signed_with_a_different_algorithm_is_rejected() -> None:
    token = jwt.encode({"sub": "42", "exp": LATER}, KEY, algorithm="HS512")

    assert read_access_token(token, KEY) is None


@pytest.mark.parametrize(
    "claims",
    [{"exp": LATER}, {"sub": "42"}, {"sub": 42, "exp": LATER}],
    ids=["no-subject", "never-expires", "subject-is-not-a-string"],
)
def test_token_with_missing_or_wrong_claims_is_rejected(
    claims: dict[str, object],
) -> None:
    token = jwt.encode(claims, KEY, algorithm="HS256")

    assert read_access_token(token, KEY) is None


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer xyz"])
def test_garbage_is_rejected(garbage: str) -> None:
    assert read_access_token(garbage, KEY) is None
