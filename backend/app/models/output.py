from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_uuid
from app.db.base import Base


class ValveReadinessSummary(Base):
    __tablename__ = "valve_readiness_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["planning_run_id", "valve_id"],
            ["valves.planning_run_id", "valves.valve_id"],
            name="fk_valve_readiness_summaries_run_valve",
        ),
        UniqueConstraint("planning_run_id", "valve_id", name="uq_valve_readiness_summaries_run_valve"),
        CheckConstraint("value_cr >= 0", name="ck_valve_readiness_summaries_value_cr_nonnegative"),
        CheckConstraint("total_components >= 0", name="ck_valve_readiness_summaries_total_components_nonnegative"),
        CheckConstraint("ready_components >= 0", name="ck_valve_readiness_summaries_ready_components_nonnegative"),
        CheckConstraint("required_components >= 0", name="ck_valve_readiness_summaries_required_components_nonnegative"),
        CheckConstraint(
            "ready_required_count >= 0",
            name="ck_valve_readiness_summaries_ready_required_count_nonnegative",
        ),
        CheckConstraint(
            "pending_required_count >= 0",
            name="ck_valve_readiness_summaries_pending_required_count_nonnegative",
        ),
        CheckConstraint("full_kit_flag in (0, 1)", name="ck_valve_readiness_summaries_full_kit_flag_bool"),
        CheckConstraint("near_ready_flag in (0, 1)", name="ck_valve_readiness_summaries_near_ready_flag_bool"),
        CheckConstraint(
            "otd_delay_days >= 0",
            name="ck_valve_readiness_summaries_otd_delay_days_nonnegative",
        ),
        CheckConstraint("otd_risk_flag in (0, 1)", name="ck_valve_readiness_summaries_otd_risk_flag_bool"),
        CheckConstraint(
            "readiness_status in ('READY', 'NEAR_READY', 'NOT_READY', 'AT_RISK', 'DATA_INCOMPLETE')",
            name="ck_valve_readiness_summaries_readiness_status",
        ),
        CheckConstraint(
            "valve_flow_imbalance_flag in (0, 1)",
            name="ck_valve_readiness_summaries_valve_flow_imbalance_flag_bool",
        ),
        Index("ix_valve_readiness_summaries_run_status", "planning_run_id", "readiness_status"),
        Index("ix_valve_readiness_summaries_run_otd_risk", "planning_run_id", "otd_risk_flag"),
        Index("ix_valve_readiness_summaries_run_assembly_date", "planning_run_id", "assembly_date"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    valve_id: Mapped[str] = mapped_column(String, nullable=False)
    customer: Mapped[str] = mapped_column(String, nullable=False)
    assembly_date: Mapped[str] = mapped_column(String, nullable=False)
    dispatch_date: Mapped[str] = mapped_column(String, nullable=False)
    value_cr: Mapped[float] = mapped_column(nullable=False)
    total_components: Mapped[int] = mapped_column(nullable=False)
    ready_components: Mapped[int] = mapped_column(nullable=False)
    required_components: Mapped[int] = mapped_column(nullable=False)
    ready_required_count: Mapped[int] = mapped_column(nullable=False)
    pending_required_count: Mapped[int] = mapped_column(nullable=False)
    full_kit_flag: Mapped[int] = mapped_column(nullable=False)
    near_ready_flag: Mapped[int] = mapped_column(nullable=False)
    valve_expected_completion_offset_days: Mapped[float | None] = mapped_column(nullable=True)
    valve_expected_completion_date: Mapped[str | None] = mapped_column(String, nullable=True)
    otd_delay_days: Mapped[float] = mapped_column(nullable=False)
    otd_risk_flag: Mapped[int] = mapped_column(nullable=False)
    readiness_status: Mapped[str] = mapped_column(String, nullable=False)
    risk_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    valve_flow_gap_days: Mapped[float | None] = mapped_column(nullable=True)
    valve_flow_imbalance_flag: Mapped[int] = mapped_column(nullable=False)
