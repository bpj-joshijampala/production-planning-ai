from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class CurrentUserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    active: bool


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user_endpoint(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role,
        active=bool(current_user.active),
    )
