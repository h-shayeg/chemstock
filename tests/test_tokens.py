import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from chemstock.tokens import AccessClaims, create_access_token, read_access_token

KEY = "k" * 64
OTHER_KEY = "o" * 64
LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)
LATER = datetime.now(UTC) + timedelta(hours=1)


def test_round_trip() -> None:
    token = create_access_token("42", KEY, timedelta(minutes=5))

    assert read_access_token(token, KEY) == AccessClaims("42", 0)


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


def test_small_clock_differences_are_tolerated() -> None:
    now = datetime.now(UTC)
    # Issued "in the future": this machine's clock moved back a little.
    from_the_future = create_access_token(
        "42", KEY, timedelta(minutes=5), now=now + timedelta(seconds=5)
    )
    # Expired a few seconds ago: the clock moved forward a little.
    just_expired = create_access_token(
        "42", KEY, timedelta(minutes=5), now=now - timedelta(minutes=5, seconds=5)
    )

    assert read_access_token(from_the_future, KEY) == AccessClaims("42", 0)
    assert read_access_token(just_expired, KEY) == AccessClaims("42", 0)


def test_large_clock_differences_are_not_tolerated() -> None:
    now = datetime.now(UTC)
    far_future = create_access_token(
        "42", KEY, timedelta(minutes=5), now=now + timedelta(minutes=5)
    )
    long_expired = create_access_token(
        "42", KEY, timedelta(minutes=5), now=now - timedelta(minutes=7)
    )

    assert read_access_token(far_future, KEY) is None
    assert read_access_token(long_expired, KEY) is None


def test_version_is_carried_in_the_token() -> None:
    token = create_access_token("42", KEY, timedelta(minutes=5), version=7)

    assert read_access_token(token, KEY) == AccessClaims("42", 7)


@pytest.mark.parametrize(
    "version", ["0", True, 1.5, None], ids=["string", "boolean", "float", "null"]
)
def test_token_with_a_bad_version_is_rejected(version: object) -> None:
    claims = {"sub": "42", "ver": version, "exp": LATER}
    token = jwt.encode(claims, KEY, algorithm="HS256")

    assert read_access_token(token, KEY) is None


def test_token_without_a_version_is_rejected() -> None:
    token = jwt.encode({"sub": "42", "exp": LATER}, KEY, algorithm="HS256")

    assert read_access_token(token, KEY) is None
