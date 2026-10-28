"""Access tokens: JWTs signed with HS256.

A token only says WHO the user is (the subject), which token VERSION the user had
when it was issued, and WHEN it expires. What the user may do is always read from
the database, never from the token. Changing the password raises the user's
version, so every older token stops working.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"
# Machines never agree exactly on the time, and a clock can jump (for example
# after a laptop wakes up). Differences up to this are tolerated.
CLOCK_SKEW_LEEWAY = timedelta(seconds=30)


@dataclass(frozen=True)
class AccessClaims:
    subject: str
    version: int


def create_access_token(
    subject: str,
    secret_key: str,
    expires_in: timedelta,
    now: datetime | None = None,
    version: int = 0,
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = {
        "sub": subject,
        "ver": version,
        "iat": issued_at,
        "exp": issued_at + expires_in,
    }
    return jwt.encode(claims, secret_key, algorithm=ALGORITHM)


def read_access_token(token: str, secret_key: str) -> AccessClaims | None:
    """Return the claims of a valid token, or None for any problem at all.

    Only HS256 is accepted (so "alg: none" and other tricks fail), and a token
    must carry an expiry, a subject and a version. Clocks may differ by up to
    CLOCK_SKEW_LEEWAY.
    """
    try:
        claims = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            leeway=CLOCK_SKEW_LEEWAY,
            options={"require": ["exp", "sub", "ver"]},
        )
    except jwt.InvalidTokenError:
        return None
    subject = claims.get("sub")
    version = claims.get("ver")
    if not isinstance(subject, str):
        return None
    if isinstance(version, bool) or not isinstance(version, int):
        return None
    return AccessClaims(subject, version)
