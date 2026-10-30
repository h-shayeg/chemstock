from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chemstock.db import get_engine
from chemstock.models import AuthAttempt
from chemstock.throttle import (
    CHANGE_PASSWORD,
    LOGIN,
    Limits,
    TooManyAttempts,
    clear_attempts,
    reserve_attempt,
)

T0 = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
LIMITS = Limits(per_username=3, per_ip=6, window=timedelta(minutes=15))
IP = "10.0.0.1"


def _reserve(
    session: Session,
    username: str = "alice",
    ip: str = IP,
    scope: str = LOGIN,
    now: datetime = T0,
) -> None:
    reserve_attempt(session, scope, username, ip, LIMITS, now=now)


def _count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AuthAttempt)) or 0


def test_attempts_are_allowed_up_to_the_limit_then_blocked(session: Session) -> None:
    for _ in range(3):
        _reserve(session)

    with pytest.raises(TooManyAttempts):
        _reserve(session)


def test_a_blocked_attempt_is_not_recorded(session: Session) -> None:
    for _ in range(3):
        _reserve(session)

    with pytest.raises(TooManyAttempts):
        _reserve(session)

    assert _count(session) == 3


def test_one_username_does_not_block_another(session: Session) -> None:
    for _ in range(3):
        _reserve(session, "alice")

    _reserve(session, "bob")  # does not raise


def test_one_address_does_not_block_another(session: Session) -> None:
    for _ in range(3):
        _reserve(session, "alice", "10.0.0.1")

    _reserve(session, "alice", "10.0.0.2")  # does not raise


def test_the_per_address_limit_covers_all_usernames(session: Session) -> None:
    for index in range(6):
        _reserve(session, f"user-{index}")

    with pytest.raises(TooManyAttempts):
        _reserve(session, "someone-new")


def test_scopes_are_independent(session: Session) -> None:
    for _ in range(3):
        _reserve(session, scope=LOGIN)

    _reserve(session, scope=CHANGE_PASSWORD)  # does not raise


def test_retry_after_is_the_time_until_the_oldest_attempt_expires(
    session: Session,
) -> None:
    for minutes in (0, 1, 2):
        _reserve(session, now=T0 + timedelta(minutes=minutes))

    with pytest.raises(TooManyAttempts) as blocked:
        _reserve(session, now=T0 + timedelta(minutes=3))

    assert blocked.value.retry_after == 12 * 60
    # Exactly when the oldest attempt leaves the window, a new try is allowed.
    _reserve(session, now=T0 + timedelta(minutes=15))


def test_old_attempts_leave_the_window_and_are_cleaned_up(session: Session) -> None:
    for _ in range(3):
        _reserve(session, now=T0)

    _reserve(session, now=T0 + LIMITS.window + timedelta(seconds=1))

    assert _count(session) == 1


def test_clear_attempts_resets_only_that_user_and_address(session: Session) -> None:
    for _ in range(3):
        _reserve(session, "alice")
    _reserve(session, "bob")
    _reserve(session, "alice", "10.0.0.2")

    clear_attempts(session, LOGIN, "  ALICE ", IP)

    assert _count(session) == 2
    for _ in range(3):
        _reserve(session, "alice")  # allowed again


def test_usernames_are_stored_normalized_and_capped(session: Session) -> None:
    _reserve(session, "  AlIcE ")
    _reserve(session, "x" * 500)

    names = sorted(session.scalars(select(AuthAttempt.username)))

    assert names == ["alice", "x" * 100]


def test_parallel_attempts_cannot_exceed_the_limit(session: Session) -> None:
    def attempt(_: int) -> bool:
        with Session(get_engine()) as worker_session:
            try:
                reserve_attempt(worker_session, LOGIN, "alice", IP, LIMITS)
            except TooManyAttempts:
                return False
            return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(12)))

    assert results.count(True) == 3
    assert _count(session) == 3
