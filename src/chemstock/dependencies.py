"""FastAPI dependencies that identify who is calling and what they may do."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from chemstock.config import get_settings
from chemstock.db import get_session
from chemstock.models import User
from chemstock.roles import ROLE_RANK, Role
from chemstock.tokens import read_access_token

MAX_USER_ID = 2_147_483_647  # largest value of a PostgreSQL "integer" column

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
    )


def user_from_token(token: str, session: Session) -> User | None:
    """The active user a token belongs to, or None. The database has the final word.

    Shared by the API (token in the Authorization header) and the web pages
    (token in a cookie, see chemstock.web).
    """
    claims = read_access_token(token, get_settings().secret_key.get_secret_value())
    if claims is None:
        return None
    subject = claims.subject
    if not (subject.isascii() and subject.isdecimal()):
        return None
    user_id = int(subject)
    if not 1 <= user_id <= MAX_USER_ID:
        return None
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    if user.token_version != claims.version:
        return None  # the password changed after this token
    return user


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """The active user the token belongs to (see user_from_token)."""
    user = user_from_token(token, session)
    if user is None:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def has_role(user: User, minimum: Role) -> bool:
    return ROLE_RANK[Role(user.role)] >= ROLE_RANK[minimum]


def require_access(request: Request, user: CurrentUser) -> User:
    """Default policy of the inventory API.

    Reading needs at least "viewer"; anything that changes data (POST, PUT,
    PATCH, DELETE) needs at least "member". Applied to whole routers, so a new
    endpoint is protected from its first day.
    """
    minimum = Role.VIEWER if request.method in SAFE_METHODS else Role.MEMBER
    if not has_role(user, minimum):
        raise _forbidden()
    return user


def require_role(minimum: Role) -> Callable[[User], User]:
    """Dependency factory: the caller must have at least this role."""

    def check(user: CurrentUser) -> User:
        if not has_role(user, minimum):
            raise _forbidden()
        return user

    return check
