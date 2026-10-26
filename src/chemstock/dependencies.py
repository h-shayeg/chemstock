"""FastAPI dependencies that identify who is calling."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from chemstock.config import get_settings
from chemstock.db import get_session
from chemstock.models import User
from chemstock.tokens import read_access_token

MAX_USER_ID = 2_147_483_647  # largest value of a PostgreSQL "integer" column

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """The active user the token belongs to. The database has the final word."""
    subject = read_access_token(token, get_settings().secret_key.get_secret_value())
    if subject is None or not (subject.isascii() and subject.isdecimal()):
        raise _unauthorized()
    user_id = int(subject)
    if not 1 <= user_id <= MAX_USER_ID:
        raise _unauthorized()
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
