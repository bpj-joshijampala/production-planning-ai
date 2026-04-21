from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role in ('PLANNER', 'HOD', 'MANAGEMENT', 'ADMIN')", name="ck_users_role"),
        CheckConstraint("active in (0, 1)", name="ck_users_active_bool"),
        Index("ix_users_role", "role"),
        Index("ix_users_active", "active"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str | None] = mapped_column(String, nullable=True)
