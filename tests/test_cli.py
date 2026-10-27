import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from chemstock import cli
from chemstock.models import User
from chemstock.security import verify_password

PASSWORD = "a long enough password"


def _type(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    replies = iter(answers)
    monkeypatch.setattr(cli, "getpass", lambda prompt="": next(replies))


def test_create_user_command(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _type(monkeypatch, PASSWORD, PASSWORD)

    assert cli.main(["create-user", "Alice", "--role", "admin"]) == 0

    user = session.scalars(select(User)).one()
    assert (user.username, user.role) == ("alice", "admin")
    assert verify_password(PASSWORD, user.hashed_password)
    output = capsys.readouterr().out
    assert "alice" in output
    assert PASSWORD not in output


def test_default_role_is_member(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _type(monkeypatch, PASSWORD, PASSWORD)

    assert cli.main(["create-user", "bob"]) == 0

    assert session.scalars(select(User)).one().role == "member"


def test_mismatched_passwords_create_nothing(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _type(monkeypatch, PASSWORD, "something else entirely")

    assert cli.main(["create-user", "alice"]) == 1

    assert "do not match" in capsys.readouterr().err
    assert session.scalars(select(User)).all() == []


def test_invalid_input_is_reported_not_raised(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _type(monkeypatch, "short", "short")

    assert cli.main(["create-user", "alice"]) == 1

    assert "Error:" in capsys.readouterr().err
    assert session.scalars(select(User)).all() == []


def test_duplicate_username_is_reported(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _type(monkeypatch, PASSWORD, PASSWORD, PASSWORD, PASSWORD)

    assert cli.main(["create-user", "alice"]) == 0
    assert cli.main(["create-user", "ALICE"]) == 1

    assert "already taken" in capsys.readouterr().err


def test_set_owner_command(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _type(monkeypatch, PASSWORD, PASSWORD)
    assert cli.main(["create-user", "alice", "--role", "admin"]) == 0
    capsys.readouterr()

    assert cli.main(["set-owner", "Alice"]) == 0

    assert session.scalars(select(User)).one().role == "owner"
    assert "'alice' is now the owner" in capsys.readouterr().out


def test_set_owner_reports_an_unknown_user(
    session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["set-owner", "ghost"]) == 1

    assert "Error:" in capsys.readouterr().err


def test_owner_role_cannot_be_given_with_create_user() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["create-user", "alice", "--role", "owner"])

    assert exit_info.value.code == 2
