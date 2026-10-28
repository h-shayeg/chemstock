from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from chemstock.config import get_settings
from chemstock.db import get_session
from chemstock.dependencies import CurrentUser
from chemstock.models import User
from chemstock.schemas import PasswordChange, TokenRead, UserRead
from chemstock.security import hash_password, verify_password
from chemstock.tokens import create_access_token
from chemstock.users import (
    MAX_PASSWORD_LENGTH,
    UserError,
    authenticate_user,
    validate_password,
)

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
        str(user.id),
        settings.secret_key.get_secret_value(),
        expires_in,
        version=user.token_version,
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


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange, user: CurrentUser, session: SessionDep
) -> None:
    """Change your own password.

    You must give the current password. Afterwards every access token issued
    before the change stops working, so log in again.
    """
    current_is_right = len(
        payload.current_password
    ) <= MAX_PASSWORD_LENGTH and verify_password(
        payload.current_password, user.hashed_password
    )
    if not current_is_right:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Current password is incorrect"
        )
    try:
        validate_password(payload.new_password)
    except UserError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from None
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The new password must be different from the current one",
        )
    user.hashed_password = hash_password(payload.new_password)
    # The increment happens inside the database, so two changes at the same
    # moment cannot overwrite each other's count.
    user.token_version = User.token_version + 1
    session.commit()
