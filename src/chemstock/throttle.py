"""Slowing down password guessing.

Every login, and every password change, first RESERVES an attempt and only then
checks the password. A correct password erases the reservation, so what piles up
are failures. The reservation is written before the (slow) password check, and
attempts from one address are handled one at a time, so parallel requests see
each other and cannot slip past the limit.

State lives in the database (table auth_attempts): it survives restarts and is
shared by several API processes.

Limits are counted inside a sliding window:
- per username AND client address, so a stranger cannot lock a user out of their
  own address just by guessing the name from somewhere else;
- per client address in total, so one address cannot try many names.

A request that is turned away is NOT recorded, and its password is not even
checked, so a correct guess during a lockout does not help.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from chemstock.config import get_settings
from chemstock.models import AuthAttempt
from chemstock.users import normalize_username

LOGIN = "login"
CHANGE_PASSWORD = "change-password"
MAX_NAME_LENGTH = 100  # the size of the column; longer names are cut
MAX_IP_LENGTH = 45  # long enough for an IPv6 address


@dataclass(frozen=True)
class Limits:
    per_username: int = 5
    per_ip: int = 20
    window: timedelta = timedelta(minutes=15)


class TooManyAttempts(Exception):
    """A limit is reached. retry_after is a number of whole seconds."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"too many attempts, retry in {retry_after} s")
        self.retry_after = retry_after


def get_limits() -> Limits:
    settings = get_settings()
    return Limits(
        per_username=settings.login_max_attempts_per_username,
        per_ip=settings.login_max_attempts_per_ip,
        window=timedelta(minutes=settings.login_lockout_minutes),
    )


def _name(username: str) -> str:
    return normalize_username(username)[:MAX_NAME_LENGTH]


def _wait(
    times: list[datetime], limit: int, window: timedelta, now: datetime
) -> timedelta | None:
    """How long until fewer than `limit` of these attempts are in the window."""
    if len(times) < limit:
        return None
    must_leave = sorted(times)[len(times) - limit]
    return must_leave + window - now


def reserve_attempt(
    session: Session,
    scope: str,
    username: str,
    ip_address: str,
    limits: Limits,
    now: datetime | None = None,
) -> None:
    """Record an attempt, or raise TooManyAttempts if a limit is reached."""
    now = now or datetime.now(UTC)
    name = _name(username)
    ip = ip_address[:MAX_IP_LENGTH]
    cutoff = now - limits.window

    # One lock per (scope, address) until the commit below: attempts from the
    # same address are counted one at a time.
    lock = text(
        "SELECT pg_advisory_xact_lock("
        "hashtextextended(CAST(:key AS text), CAST(0 AS bigint)))"
    )
    session.execute(lock, {"key": f"{scope}|{ip}"})

    session.execute(delete(AuthAttempt).where(AuthAttempt.attempted_at <= cutoff))
    from_this_address = (
        AuthAttempt.scope == scope,
        AuthAttempt.ip_address == ip,
        AuthAttempt.attempted_at > cutoff,
    )
    by_address = list(
        session.scalars(select(AuthAttempt.attempted_at).where(*from_this_address))
    )
    by_username = list(
        session.scalars(
            select(AuthAttempt.attempted_at).where(
                *from_this_address, AuthAttempt.username == name
            )
        )
    )

    waits = [
        wait
        for wait in (
            _wait(by_username, limits.per_username, limits.window, now),
            _wait(by_address, limits.per_ip, limits.window, now),
        )
        if wait is not None
    ]
    if waits:
        session.commit()  # keeps the clean-up and releases the lock
        raise TooManyAttempts(max(1, math.ceil(max(waits).total_seconds())))

    session.add(
        AuthAttempt(scope=scope, username=name, ip_address=ip, attempted_at=now)
    )
    session.commit()


def clear_attempts(
    session: Session, scope: str, username: str, ip_address: str
) -> None:
    """Forget the attempts of one username from one address (after a success)."""
    session.execute(
        delete(AuthAttempt).where(
            AuthAttempt.scope == scope,
            AuthAttempt.username == _name(username),
            AuthAttempt.ip_address == ip_address[:MAX_IP_LENGTH],
        )
    )
    session.commit()
