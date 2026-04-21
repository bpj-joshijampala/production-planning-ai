from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.db.base import Base


class PlanningRun(Base):
    __tablename__ = "planning_runs"
    __table_args__ = (
        CheckConstraint("planning_horizon_days in (7, 14)", name="ck_planning_runs_horizon"),
        CheckConstraint("status in ('CREATED', 'CALCULATING', 'CALCULATED', 'FAILED')", name="ck_planning_runs_status"),
        Index("ix_planning_runs_upload_batch_id", "upload_batch_id"),
        Index("ix_planning_runs_created_at", "created_at"),
        Index("ix_planning_runs_status", "status"),
        Index("ix_planning_runs_planning_start_date", "planning_start_date"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    upload_batch_id: Mapped[str] = mapped_column(ForeignKey("upload_batches.id"), nullable=False)
    planning_start_date: Mapped[str] = mapped_column(String, nullable=False)
    planning_horizon_days: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="CREATED")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    calculated_at: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)


class PlanningSnapshot(Base):
    __tablename__ = "planning_snapshots"
    __table_args__ = (
        CheckConstraint("json_valid(snapshot_json)", name="ck_planning_snapshots_snapshot_json"),
        UniqueConstraint("planning_run_id", name="uq_planning_snapshots_planning_run_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class MasterDataVersion(Base):
    __tablename__ = "master_data_versions"
    __table_args__ = (UniqueConstraint("planning_run_id", name="uq_master_data_versions_planning_run_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    routing_version_hash: Mapped[str] = mapped_column(String, nullable=False)
    machine_version_hash: Mapped[str] = mapped_column(String, nullable=False)
    vendor_version_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
