from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from chemstock.authority import may_assign, may_manage
from chemstock.db import get_session
from chemstock.dependencies import CurrentUser, require_role
from chemstock.models import User
from chemstock.roles import Role
from chemstock.schemas import UserCreate, UserRead, UserUpdate
from chemstock.users import UserError, UsernameTakenError, create_user

# Only admins and the owner may use this router; the rules below decide who may
# change whom.
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)

SessionDep = Annotated[Session, Depends(get_session)]
# Upper bound = largest value of a PostgreSQL "integer" column.
UserId = Annotated[int, Path(ge=1, le=2_147_483_647)]


def _get_or_404(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreate, actor: CurrentUser, session: SessionDep
) -> User:
    """Create a user. You can only give roles that rank below your own."""
    if not may_assign(Role(actor.role), payload.role):
        raise _forbidden("You cannot create a user with a role this high")
    try:
        return create_user(session, payload.username, payload.password, payload.role)
    except UsernameTakenError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    except UserError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from None


@router.get("", response_model=list[UserRead])
def list_users(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    statement = select(User).order_by(User.id).limit(limit).offset(offset)
    return list(session.scalars(statement))


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UserId, session: SessionDep) -> User:
    return _get_or_404(session, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: UserId, payload: UserUpdate, actor: CurrentUser, session: SessionDep
) -> User:
    """Change the role or the active flag of a user ranking below you.

    Nobody can change their own account. The owner role can never be given.
    """
    target = _get_or_404(session, user_id)
    if target.id == actor.id:
        raise _forbidden("You cannot change your own role or status")
    if not may_manage(Role(actor.role), Role(target.role)):
        raise _forbidden("You can only change accounts that rank below yours")
    if payload.role is not None and not may_assign(Role(actor.role), payload.role):
        raise _forbidden("You cannot give a role this high")
    if payload.role is not None:
        target.role = payload.role.value
    if payload.is_active is not None:
        target.is_active = payload.is_active
    session.commit()
    session.refresh(target)
    return target
