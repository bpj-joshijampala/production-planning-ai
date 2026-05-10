from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User

DEFAULT_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
VIEW_ROLES = ("PLANNER", "HOD", "MANAGEMENT", "ADMIN")
WRITE_ROLES = ("PLANNER",)
EXPORT_ROLES = ("PLANNER", "HOD", "MANAGEMENT")


def load_acting_user(*, user_id: str, db: Session) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "ACTING_USER_NOT_FOUND",
                "message": f"Acting user {user_id} was not found.",
            },
        )
    if user.active != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACTING_USER_INACTIVE",
                "message": "Acting user is inactive and cannot perform this action.",
            },
        )
    return user


def ensure_user_role(user: User, *, allowed_roles: tuple[str, ...]) -> User:
    if user.role not in set(allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ROLE_NOT_ALLOWED",
                "message": f"Role {user.role} is not allowed to perform this action.",
            },
        )
    return user


def load_acting_user_for_roles(*, user_id: str, db: Session, allowed_roles: tuple[str, ...]) -> User:
    return ensure_user_role(load_acting_user(user_id=user_id, db=db), allowed_roles=allowed_roles)


def get_current_user(db: Session = Depends(get_db)) -> User:
    return load_acting_user(user_id=DEFAULT_DEV_USER_ID, db=db)


def require_current_user_roles(*allowed_roles: str) -> Callable[[User], User]:
    allowed_role_set = set(allowed_roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        return ensure_user_role(current_user, allowed_roles=tuple(allowed_role_set))

    return dependency
