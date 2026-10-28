"""Creating users and checking their credentials (no HTTP here)."""

import re

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.models import User
from chemstock.roles import Role
from chemstock.security import DUMMY_HASH, hash_password, verify_password

USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{2,49}")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class UserError(ValueError):
    """The data given for a new user is not acceptable."""


class UsernameTakenError(UserError):
    """A user with this username already exists."""


def normalize_username(username: str) -> str:
    """Usernames are case-insensitive: they are stored in lower case."""
    return username.strip().casefold()


def validate_password(password: str) -> None:
    """Raise UserError unless the password has an acceptable length."""
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise UserError(
            f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} "
            "characters long."
        )


def create_user(
    session: Session, username: str, password: str, role: Role | str
) -> User:
    name = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(name):
        raise UserError(
            "Username must be 3-50 characters: lowercase letters, digits, '_', "
            "'.' or '-', starting with a letter or a digit."
        )
    validate_password(password)
    try:
        role_value = Role(role).value
    except ValueError:
        raise UserError(f"Unknown role {role!r}.") from None
    if role_value == Role.OWNER.value:
        raise UserError(
            "The owner role can only be given with the set-owner command."
        )

    user = User(
        username=name, hashed_password=hash_password(password), role=role_value
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise UsernameTakenError(f"Username '{name}' is already taken.") from None
    session.refresh(user)
    return user


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    """Return the user if the credentials are right and the account is active.

    "No such user", "wrong password" and "inactive account" all give None, so
    callers cannot tell them apart.
    """
    user = session.scalar(
        select(User).where(User.username == normalize_username(username))
    )
    if user is None:
        verify_password(password, DUMMY_HASH)
        return None
    password_is_right = verify_password(password, user.hashed_password)
    return user if password_is_right and user.is_active else None


def set_owner(session: Session, username: str) -> tuple[User, str | None]:
    """Make an existing, active user the owner (the one main admin).

    The previous owner, if there is one, becomes an admin. Returns the new owner
    and the username of the previous owner (None if there was none).
    """
    name = normalize_username(username)
    target = session.scalar(select(User).where(User.username == name))
    if target is None:
        raise UserError(f"There is no user named '{name}'.")
    if not target.is_active:
        raise UserError("An inactive user cannot become the owner.")
    current = session.scalar(select(User).where(User.role == Role.OWNER.value))
    if current is not None and current.id == target.id:
        return target, None
    previous = current.username if current is not None else None
    # Order matters: the old owner must be demoted before the new one is promoted,
    # or the "one owner only" index would be violated for a moment.
    if current is not None:
        session.execute(
            update(User).where(User.id == current.id).values(role=Role.ADMIN.value)
        )
    session.execute(
        update(User).where(User.id == target.id).values(role=Role.OWNER.value)
    )
    session.commit()
    session.refresh(target)
    return target, previous
