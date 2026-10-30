from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from chemstock.authority import may_assign, may_manage
from chemstock.db import get_session
from chemstock.dependencies import CurrentUser, require_role
from chemstock.models import RevokedPermission, User
from chemstock.permissions import Permission
from chemstock.roles import Role
from chemstock.schemas import PermissionsUpdate, UserCreate, UserRead, UserUpdate
from chemstock.users import UserError, UsernameTakenError, create_user

# Only admins and the owner may use this router. The rules below decide who may
# change whom (the role hierarchy) and what an admin may do (permissions).
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


def _require_permission(actor: User, permission: Permission) -> None:
    if permission.value not in actor.permissions:
        raise _forbidden(f"Missing permission: {permission.value}")


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreate, actor: CurrentUser, session: SessionDep
) -> User:
    """Create a user.

    Needs the `create_users` permission, and you can only give roles that rank
    below your own.
    """
    _require_permission(actor, Permission.CREATE_USERS)
    if not may_assign(Role(actor.role), payload.role):
        raise _forbidden("You cannot create a user with a role this high")
    try:
        return create_user(session, payload.username, payload.password, payload.role)
    except UsernameTakenError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    except UserError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from None


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

    Changing a role needs `change_roles`, and (de)activating needs
    `deactivate_users`; doing both at once needs both. Nobody can change their
    own account. The owner role can never be given.
    """
    if payload.role is not None:
        _require_permission(actor, Permission.CHANGE_ROLES)
    if payload.is_active is not None:
        _require_permission(actor, Permission.DEACTIVATE_USERS)
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


@router.put(
    "/{user_id}/permissions",
    response_model=UserRead,
    dependencies=[Depends(require_role(Role.OWNER))],
)
def set_permissions(
    user_id: UserId, payload: PermissionsUpdate, session: SessionDep
) -> User:
    """Set what an admin may do. Only the owner may call this.

    Send the complete list of permissions the admin is allowed to use; it
    replaces the old list, and an empty list takes everything away. It only
    applies to admin accounts: the owner always has every permission, and
    members and viewers cannot manage users at all.
    """
    target = _get_or_404(session, user_id)
    if Role(target.role) is not Role.ADMIN:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Permissions can only be set for admin accounts",
        )
    allowed = set(payload.permissions)
    wanted_revoked = {item.value for item in Permission if item not in allowed}
    for link in list(target.revoked_links):
        if link.permission not in wanted_revoked:
            target.revoked_links.remove(link)
    already = {link.permission for link in target.revoked_links}
    for name in sorted(wanted_revoked - already):
        target.revoked_links.append(RevokedPermission(permission=name))
    session.commit()
    session.refresh(target)
    return target
