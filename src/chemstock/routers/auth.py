from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from chemstock.config import get_settings
from chemstock.db import get_session
from chemstock.dependencies import CurrentUser
from chemstock.models import User
from chemstock.schemas import TokenRead, UserRead
from chemstock.tokens import create_access_token
from chemstock.users import MAX_PASSWORD_LENGTH, authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/login", response_model=TokenRead)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> TokenRead:
    """Exchange a username and password for an access token.

    Every kind of failure (unknown user, wrong password, inactive account)
    gives the same answer, so it does not reveal which usernames exist.
    """
    user = None
    # No valid password is this long, so skip the expensive hashing.
    if len(form.password) <= MAX_PASSWORD_LENGTH:
        user = authenticate_user(session, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    expires_in = timedelta(minutes=settings.access_token_expire_minutes)
    token = create_access_token(
        str(user.id), settings.secret_key.get_secret_value(), expires_in
    )
    return TokenRead(
        access_token=token,
        token_type="bearer",
        expires_in=int(expires_in.total_seconds()),
    )


@router.get("/me", response_model=UserRead)
def read_current_user(user: CurrentUser) -> User:
    """The user the access token belongs to."""
    return user
