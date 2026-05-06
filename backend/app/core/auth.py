from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User

DEFAULT_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
WRITE_ROLES = ("PLANNER", "ADMIN")
EXPORT_ROLES = ("PLANNER", "HOD", "MANAGEMENT", "ADMIN")


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


def get_current_user(db: Session = Depends(get_db)) -> User:
    return load_acting_user(user_id=DEFAULT_DEV_USER_ID, db=db)


def require_current_user_roles(*allowed_roles: str) -> Callable[[User], User]:
    allowed_role_set = set(allowed_roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_role_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ROLE_NOT_ALLOWED",
                    "message": f"Role {current_user.role} is not allowed to perform this action.",
                },
            )
        return current_user

    return dependency
