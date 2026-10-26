import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.models import User
from chemstock.roles import Role
from chemstock.security import DUMMY_HASH, verify_password
from chemstock.users import (
    UserError,
    UsernameTakenError,
    authenticate_user,
    create_user,
)

PASSWORD = "a long enough password"


def test_create_user_stores_a_hash_not_the_password(session: Session) -> None:
    user = create_user(session, "alice", PASSWORD, "member")

    assert user.id is not None
    assert user.role == "member"
    assert user.is_active is True
    assert user.hashed_password != PASSWORD
    assert verify_password(PASSWORD, user.hashed_password)


def test_username_is_normalized(session: Session) -> None:
    user = create_user(session, "  Alice.Smith  ", PASSWORD, Role.ADMIN)

    assert user.username == "alice.smith"
    assert user.role == "admin"


def test_duplicate_username_is_rejected_ignoring_case(session: Session) -> None:
    create_user(session, "alice", PASSWORD, "member")

    with pytest.raises(UsernameTakenError):
        create_user(session, "ALICE", PASSWORD, "viewer")

    # The session is still usable after the failure.
    assert create_user(session, "bob", PASSWORD, "viewer").username == "bob"


@pytest.mark.parametrize(
    "username",
    ["", "ab", "a" * 51, "has space", "-leading", "\u00fcn\u00efcode", "slash/name"],
)
def test_invalid_usernames_are_rejected(session: Session, username: str) -> None:
    with pytest.raises(UserError):
        create_user(session, username, PASSWORD, "member")


@pytest.mark.parametrize("password", ["", "short", "x" * 11, "x" * 129])
def test_invalid_passwords_are_rejected(session: Session, password: str) -> None:
    with pytest.raises(UserError):
        create_user(session, "alice", password, "member")


def test_password_length_boundaries_are_accepted(session: Session) -> None:
    assert create_user(session, "shortest", "x" * 12, "member").id
    assert create_user(session, "longest", "y" * 128, "member").id


def test_unknown_role_is_rejected(session: Session) -> None:
    with pytest.raises(UserError):
        create_user(session, "alice", PASSWORD, "superuser")


def test_authenticate_with_correct_credentials(session: Session) -> None:
    created = create_user(session, "alice", PASSWORD, "member")

    found = authenticate_user(session, "alice", PASSWORD)

    assert found is not None
    assert found.id == created.id


def test_authenticate_ignores_case_and_spaces_of_the_username(
    session: Session,
) -> None:
    create_user(session, "alice", PASSWORD, "member")

    assert authenticate_user(session, "  ALICE ", PASSWORD) is not None


def test_authenticate_rejects_wrong_password(session: Session) -> None:
    create_user(session, "alice", PASSWORD, "member")

    assert authenticate_user(session, "alice", "another long password") is None


def test_authenticate_rejects_unknown_user(session: Session) -> None:
    assert authenticate_user(session, "ghost", PASSWORD) is None


def test_authenticate_rejects_inactive_user(session: Session) -> None:
    user = create_user(session, "alice", PASSWORD, "member")
    user.is_active = False
    session.commit()

    assert authenticate_user(session, "alice", PASSWORD) is None


def test_unknown_user_still_costs_one_hash_verification(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def spy(password: str, hashed_password: str) -> bool:
        calls.append(hashed_password)
        return False

    monkeypatch.setattr("chemstock.users.verify_password", spy)

    assert authenticate_user(session, "ghost", PASSWORD) is None
    assert calls == [DUMMY_HASH]


def test_database_rejects_unknown_role(session: Session) -> None:
    session.add(User(username="mallory", hashed_password="x", role="root"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_username_with_capital_letters(session: Session) -> None:
    session.add(User(username="Mallory", hashed_password="x", role="member"))

    with pytest.raises(IntegrityError):
        session.commit()
