"""Access tokens: JWTs signed with HS256.

A token only says WHO the user is (the subject) and WHEN it expires. What the
user may do is always read from the database, never from the token.
"""

from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"


def create_access_token(
    subject: str,
    secret_key: str,
    expires_in: timedelta,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = {"sub": subject, "iat": issued_at, "exp": issued_at + expires_in}
    return jwt.encode(claims, secret_key, algorithm=ALGORITHM)


def read_access_token(token: str, secret_key: str) -> str | None:
    """Return the subject of a valid token, or None for any problem at all.

    Only HS256 is accepted (so "alg: none" and other tricks fail), and a token
    must carry both an expiry and a subject.
    """
    try:
        claims = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    subject = claims.get("sub")
    return subject if isinstance(subject, str) else None
