from collections import defaultdict
import json

from fastapi import HTTPException, status
from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.models.canonical import ComponentStatus, Valve, Vendor
from app.models.output import (
    FlowBlocker,
    IncomingLoadItem,
    MachineLoadSummary,
    PlannedOperation,
    Recommendation,
    ThroughputSummary,
    ValveReadinessSummary,
    VendorLoadSummary,
)
from app.models.planning_run import PlanningRun
from app.schemas.dashboard import (
    AssemblyRiskItemResponse,
    AssemblyRiskListResponse,
    ComponentStatusItemResponse,
    ComponentStatusListResponse,
    FlowBlockerItemResponse,
    FlowBlockerListResponse,
    IncomingLoadItemResponse,
    IncomingLoadListResponse,
    MachineLoadListResponse,
    MachineLoadSummaryResponse,
    PlanningRunDashboardSummaryResponse,
    QueueOperationListResponse,
    QueueOperationResponse,
    RecommendationItemResponse,
    RecommendationListResponse,
    ThroughputSummaryResponse,
    ValveReadinessItemResponse,
    ValveReadinessListResponse,
    VendorLoadItemResponse,
    VendorLoadListResponse,
)

VENDOR_LIMITATION_WARNING = "Vendor timing and external pending load are only partially modeled in V1. Confirm before dispatch."


def get_dashboard_summary(planning_run_id: str, db: Session) -> PlanningRunDashboardSummaryResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    active_valves = db.scalar(
        select(func.count()).select_from(Valve).where(Valve.planning_run_id == planning_run_id)
    ) or 0
    active_value_cr = db.scalar(
        select(func.coalesce(func.sum(Valve.value_cr), 0.0)).where(Valve.planning_run_id == planning_run_id)
    ) or 0.0
    throughput = db.scalar(
        select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
    )
    overloaded_machines = db.scalar(
        select(func.count())
        .select_from(MachineLoadSummary)
        .where(MachineLoadSummary.planning_run_id == planning_run_id)
        .where(MachineLoadSummary.overload_flag == 1)
    ) or 0
    underutilized_machines = db.scalar(
        select(func.count())
        .select_from(MachineLoadSummary)
        .where(MachineLoadSummary.planning_run_id == planning_run_id)
        .where(MachineLoadSummary.underutilized_flag == 1)
    ) or 0
    flow_blockers = db.scalar(
        select(func.count()).select_from(FlowBlocker).where(FlowBlocker.planning_run_id == planning_run_id)
    ) or 0
    assembly_risk_valves = db.scalar(
        select(func.count())
        .select_from(ValveReadinessSummary)
        .where(ValveReadinessSummary.planning_run_id == planning_run_id)
        .where(ValveReadinessSummary.otd_risk_flag == 1)
    ) or 0
    subcontract_recommendations = db.scalar(
        select(func.count())
        .select_from(Recommendation)
        .where(Recommendation.planning_run_id == planning_run_id)
        .where(Recommendation.recommendation_type.in_(("SUBCONTRACT", "BATCH_SUBCONTRACT_OPPORTUNITY")))
    ) or 0
    batch_risks = db.scalar(
        select(func.count())
        .select_from(FlowBlocker)
        .where(FlowBlocker.planning_run_id == planning_run_id)
        .where(FlowBlocker.blocker_type == "BATCH_RISK")
    ) or 0

    return PlanningRunDashboardSummaryResponse(
        planning_run_id=planning_run_id,
        active_valves=active_valves,
        active_value_cr=float(active_value_cr),
        planned_throughput_value_cr=0.0 if throughput is None else float(throughput.planned_throughput_value_cr),
        throughput_gap_cr=0.0 if throughput is None else float(throughput.throughput_gap_cr),
        overloaded_machines=overloaded_machines,
        underutilized_machines=underutilized_machines,
        flow_blockers=flow_blockers,
        assembly_risk_valves=assembly_risk_valves,
        subcontract_recommendations=subcontract_recommendations,
        batch_risks=batch_risks,
    )


def list_incoming_load(
    planning_run_id: str,
    db: Session,
    *,
    page: int,
    page_size: int,
    sort: str | None,
    direction: str,
    customer: str | None,
    valve_type: str | None,
    machine_type: str | None,
    date_confidence: str | None,
    availability_from: str | None,
    availability_to: str | None,
) -> IncomingLoadListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    query = (
        select(IncomingLoadItem, Valve.customer, Valve.valve_type)
        .join(
            Valve,
            (Valve.planning_run_id == IncomingLoadItem.planning_run_id) & (Valve.valve_id == IncomingLoadItem.valve_id),
        )
        .where(IncomingLoadItem.planning_run_id == planning_run_id)
    )
    if customer:
        query = query.where(Valve.customer == customer)
    if valve_type:
        query = query.where(Valve.valve_type == valve_type)
    if machine_type:
        query = query.where(IncomingLoadItem.machine_types_json.contains(f'"{machine_type.strip()}"'))
    if date_confidence:
        query = query.where(IncomingLoadItem.date_confidence == date_confidence)
    if availability_from:
        query = query.where(IncomingLoadItem.availability_date >= availability_from)
    if availability_to:
        query = query.where(IncomingLoadItem.availability_date <= availability_to)

    query = _apply_sort(
        query,
        sort=sort,
        direction=direction,
        mapping={
            "availability_date": IncomingLoadItem.availability_date,
            "priority_score": IncomingLoadItem.priority_score,
            "sort_sequence": IncomingLoadItem.sort_sequence,
            "valve_id": IncomingLoadItem.valve_id,
            "component": IncomingLoadItem.component,
            "customer": Valve.customer,
            "valve_type": Valve.valve_type,
            "machine_type": IncomingLoadItem.machine_types_json,
            "date_confidence": IncomingLoadItem.date_confidence,
        },
        default=(
            IncomingLoadItem.availability_date.asc(),
            IncomingLoadItem.priority_score.desc(),
            IncomingLoadItem.machine_types_json.asc(),
            IncomingLoadItem.id.asc(),
        ),
        tie_breakers=(IncomingLoadItem.sort_sequence.asc(), IncomingLoadItem.id.asc()),
    )
    total, rows = _paginate(db, query, page=page, page_size=page_size)

    return IncomingLoadListResponse(
        items=[
            IncomingLoadItemResponse(
                valve_id=row.IncomingLoadItem.valve_id,
                customer=row.customer,
                valve_type=row.valve_type,
                component_line_no=row.IncomingLoadItem.component_line_no,
                component=row.IncomingLoadItem.component,
                qty=float(row.IncomingLoadItem.qty),
                availability_date=row.IncomingLoadItem.availability_date,
                date_confidence=row.IncomingLoadItem.date_confidence,
                current_ready_flag=bool(row.IncomingLoadItem.current_ready_flag),
                machine_types=_parse_json_array(row.IncomingLoadItem.machine_types_json),
                priority_score=float(row.IncomingLoadItem.priority_score),
                sort_sequence=row.IncomingLoadItem.sort_sequence,
                same_day_arrival_load_days=row.IncomingLoadItem.same_day_arrival_load_days,
                batch_risk_flag=bool(row.IncomingLoadItem.batch_risk_flag),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_machine_load(
    planning_run_id: str,
    db: Session,
    *,
    page: int,
    page_size: int,
    sort: str | None,
    direction: str,
    status_filter: str | None,
) -> MachineLoadListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    query = select(MachineLoadSummary).where(MachineLoadSummary.planning_run_id == planning_run_id)
    if status_filter:
        query = query.where(MachineLoadSummary.status == status_filter)
    extreme_delay_count = (
        select(func.count())
        .select_from(PlannedOperation)
        .where(PlannedOperation.planning_run_id == MachineLoadSummary.planning_run_id)
        .where(PlannedOperation.machine_type == MachineLoadSummary.machine_type)
        .where(PlannedOperation.extreme_delay_flag == 1)
        .correlate(MachineLoadSummary)
        .scalar_subquery()
    )
    overloaded_priority = case((MachineLoadSummary.status == "OVERLOADED", 0), else_=1)
    extreme_delay_priority = case((extreme_delay_count > 0, 0), else_=1)
    batch_risk_priority = case((MachineLoadSummary.batch_risk_flag == 1, 0), else_=1)
    underutilized_priority = case((MachineLoadSummary.status == "UNDERUTILIZED", 1), else_=0)
    query = _apply_sort(
        query,
        sort=sort,
        direction=direction,
        mapping={
            "machine_type": MachineLoadSummary.machine_type,
            "load_days": MachineLoadSummary.load_days,
            "status": MachineLoadSummary.status,
            "overload_days": MachineLoadSummary.overload_days,
            "spare_capacity_days": MachineLoadSummary.spare_capacity_days,
            "batch_risk": MachineLoadSummary.batch_risk_flag,
            "underutilized": MachineLoadSummary.underutilized_flag,
        },
        default=(
            overloaded_priority.asc(),
            extreme_delay_priority.asc(),
            batch_risk_priority.asc(),
            MachineLoadSummary.load_days.desc(),
            underutilized_priority.asc(),
            MachineLoadSummary.machine_type.asc(),
            MachineLoadSummary.id.asc(),
        ),
        tie_breakers=(MachineLoadSummary.machine_type.asc(), MachineLoadSummary.id.asc()),
    )
    total, rows = _paginate_scalars(db, query, page=page, page_size=page_size)
    return MachineLoadListResponse(
        items=[_machine_load_summary_response(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_machine_queue(
    planning_run_id: str,
    machine_type: str,
    db: Session,
    *,
    page: int,
    page_size: int,
    sort: str | None,
    direction: str,
    customer: str | None,
    status_filter: str | None,
    date_confidence: str | None,
    kit_filter: str | None,
    recommendation_filter: str | None,
) -> QueueOperationListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    queue_warning = db.scalar(
        select(MachineLoadSummary.queue_approximation_warning)
        .where(MachineLoadSummary.planning_run_id == planning_run_id)
        .where(MachineLoadSummary.machine_type == machine_type)
    )

    query = (
        select(PlannedOperation, Valve.customer)
        .join(
            Valve,
            (Valve.planning_run_id == PlannedOperation.planning_run_id) & (Valve.valve_id == PlannedOperation.valve_id),
        )
        .join(
            ValveReadinessSummary,
            (ValveReadinessSummary.planning_run_id == PlannedOperation.planning_run_id)
            & (ValveReadinessSummary.valve_id == PlannedOperation.valve_id),
            isouter=True,
        )
        .where(PlannedOperation.planning_run_id == planning_run_id)
        .where(PlannedOperation.machine_type == machine_type)
    )
    if customer:
        query = query.where(Valve.customer == customer)
    if status_filter:
        query = query.where(PlannedOperation.recommendation_status == status_filter)
    if date_confidence:
        query = query.where(PlannedOperation.date_confidence == date_confidence)
    if recommendation_filter:
        query = query.where(PlannedOperation.recommendation_status == recommendation_filter)
    if kit_filter:
        normalized_kit_filter = kit_filter.strip().upper()
        if normalized_kit_filter == "FULL_KIT":
            query = query.where(ValveReadinessSummary.full_kit_flag == 1)
        elif normalized_kit_filter == "NEAR_READY":
            query = query.where(ValveReadinessSummary.near_ready_flag == 1)
        elif normalized_kit_filter == "FULL_KIT_OR_NEAR_READY":
            query = query.where(
                (ValveReadinessSummary.full_kit_flag == 1) | (ValveReadinessSummary.near_ready_flag == 1)
            )
    query = _apply_sort(
        query,
        sort=sort,
        direction=direction,
        mapping={
            "sort_sequence": PlannedOperation.sort_sequence,
            "priority_score": PlannedOperation.priority_score,
            "availability_date": PlannedOperation.availability_date,
            "completion_date": PlannedOperation.internal_completion_date,
            "customer": Valve.customer,
            "date_confidence": PlannedOperation.date_confidence,
            "recommendation": PlannedOperation.recommendation_status,
        },
        default=(
            PlannedOperation.sort_sequence.asc(),
            PlannedOperation.operation_no.asc(),
            PlannedOperation.id.asc(),
        ),
        tie_breakers=(PlannedOperation.sort_sequence.asc(), PlannedOperation.operation_no.asc(), PlannedOperation.id.asc()),
    )
    total, rows = _paginate(db, query, page=page, page_size=page_size)

    return QueueOperationListResponse(
        machine_type=machine_type,
        queue_approximation_warning=queue_warning,
        items=[
            QueueOperationResponse(
                id=row.PlannedOperation.id,
                sort_sequence=row.PlannedOperation.sort_sequence,
                priority_score=float(row.PlannedOperation.priority_score),
                valve_id=row.PlannedOperation.valve_id,
                customer=row.customer,
                component_line_no=row.PlannedOperation.component_line_no,
                component=row.PlannedOperation.component,
                operation_no=row.PlannedOperation.operation_no,
                operation_name=row.PlannedOperation.operation_name,
                availability_date=row.PlannedOperation.availability_date,
                date_confidence=row.PlannedOperation.date_confidence,
                operation_hours=float(row.PlannedOperation.operation_hours),
                internal_wait_days=row.PlannedOperation.internal_wait_days,
                processing_time_days=row.PlannedOperation.processing_time_days,
                internal_completion_date=row.PlannedOperation.internal_completion_date,
                recommendation_status=row.PlannedOperation.recommendation_status,
                extreme_delay_flag=None if row.PlannedOperation.extreme_delay_flag is None else bool(row.PlannedOperation.extreme_delay_flag),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_valve_readiness(
    planning_run_id: str,
    db: Session,
    *,
    page: int,
    page_size: int,
    sort: str | None,
    direction: str,
    customer: str | None,
    status_filter: str | None,
) -> ValveReadinessListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    query = select(ValveReadinessSummary).where(ValveReadinessSummary.planning_run_id == planning_run_id)
    if customer:
        query = query.where(ValveReadinessSummary.customer == customer)
    if status_filter:
        query = query.where(ValveReadinessSummary.readiness_status == status_filter)
    status_priority = case(
        (ValveReadinessSummary.readiness_status == "AT_RISK", 0),
        (ValveReadinessSummary.readiness_status == "NEAR_READY", 1),
        (ValveReadinessSummary.readiness_status == "READY", 2),
        (ValveReadinessSummary.readiness_status == "NOT_READY", 3),
        (ValveReadinessSummary.readiness_status == "DATA_INCOMPLETE", 4),
        else_=5,
    )
    query = _apply_sort(
        query,
        sort=sort,
        direction=direction,
        mapping={
            "assembly_date": ValveReadinessSummary.assembly_date,
            "dispatch_date": ValveReadinessSummary.dispatch_date,
            "status": ValveReadinessSummary.readiness_status,
            "expected_completion_date": ValveReadinessSummary.valve_expected_completion_date,
            "assembly_delay_days": ValveReadinessSummary.otd_delay_days,
            "value_cr": ValveReadinessSummary.value_cr,
            "customer": ValveReadinessSummary.customer,
        },
        default=(
            status_priority.asc(),
            ValveReadinessSummary.assembly_date.asc(),
            ValveReadinessSummary.value_cr.desc(),
            ValveReadinessSummary.valve_id.asc(),
            ValveReadinessSummary.id.asc(),
        ),
        tie_breakers=(ValveReadinessSummary.valve_id.asc(), ValveReadinessSummary.id.asc()),
    )
    total, rows = _paginate_scalars(db, query, page=page, page_size=page_size)
    return ValveReadinessListResponse(
        items=[_valve_readiness_response(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_component_status(
    planning_run_id: str,
    valve_id: str,
    db: Session,
    *,
    page: int,
    page_size: int,
) -> ComponentStatusListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    customer = db.scalar(
        select(Valve.customer)
        .where(Valve.planning_run_id == planning_run_id)
        .where(Valve.valve_id == valve_id)
    )
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "VALVE_NOT_FOUND",
                "message": f"Valve {valve_id} was not found for PlanningRun {planning_run_id}.",
            },
        )

    query = (
        select(ComponentStatus)
        .where(ComponentStatus.planning_run_id == planning_run_id)
        .where(ComponentStatus.valve_id == valve_id)
        .order_by(ComponentStatus.component_line_no.asc(), ComponentStatus.id.asc())
    )
    total, component_rows = _paginate_scalars(db, query, page=page, page_size=page_size)

    component_line_nos = [row.component_line_no for row in component_rows]
    next_operation_by_line: dict[int, PlannedOperation] = {}
    blockers_by_line: dict[int, list[FlowBlocker]] = defaultdict(list)

    if component_line_nos:
        planned_operation_rows = list(
            db.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .where(PlannedOperation.valve_id == valve_id)
                .where(PlannedOperation.component_line_no.in_(component_line_nos))
                .order_by(
                    PlannedOperation.component_line_no.asc(),
                    PlannedOperation.operation_no.asc(),
                    PlannedOperation.id.asc(),
                )
            )
        )
        for operation in planned_operation_rows:
            next_operation_by_line.setdefault(operation.component_line_no, operation)

        blocker_rows = list(
            db.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .where(FlowBlocker.valve_id == valve_id)
                .where(FlowBlocker.component_line_no.in_(component_line_nos))
                .order_by(
                    FlowBlocker.component_line_no.asc(),
                    FlowBlocker.created_at.asc(),
                    FlowBlocker.id.asc(),
                )
            )
        )
        for blocker in blocker_rows:
            if blocker.component_line_no is not None:
                blockers_by_line[blocker.component_line_no].append(blocker)

    items: list[ComponentStatusItemResponse] = []
    for row in component_rows:
        next_operation = next_operation_by_line.get(row.component_line_no)
        blocker_rows = blockers_by_line.get(row.component_line_no, [])
        blocker_types = [blocker.blocker_type for blocker in blocker_rows]
        blocker_summary = "; ".join(dict.fromkeys(blocker.cause for blocker in blocker_rows if blocker.cause)) or None

        items.append(
            ComponentStatusItemResponse(
                valve_id=row.valve_id,
                customer=customer,
                component_line_no=row.component_line_no,
                component=row.component,
                current_location=row.current_location,
                fabrication_complete=bool(row.fabrication_complete),
                critical=bool(row.critical),
                availability_date=row.expected_ready_date,
                date_confidence=row.ready_date_type,
                next_operation_name=None if next_operation is None else next_operation.operation_name,
                next_machine_type=None if next_operation is None else next_operation.machine_type,
                internal_wait_days=None if next_operation is None else next_operation.internal_wait_days,
                status=_component_status_display(row=row, blocker_types=blocker_types),
                blocker_types=blocker_types,
                blocker_summary=blocker_summary,
            )
        )

    return ComponentStatusListResponse(
        valve_id=valve_id,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def list_assembly_risk(
    planning_run_id: str,
    db: Session,
    *,
    page: int,
    page_size: int,
    customer: str | None,
) -> AssemblyRiskListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    query = (
        select(ValveReadinessSummary)
        .where(ValveReadinessSummary.planning_run_id == planning_run_id)
        .where(ValveReadinessSummary.otd_risk_flag == 1)
    )
    if customer:
        query = query.where(ValveReadinessSummary.customer == customer)
    query = query.order_by(
        ValveReadinessSummary.otd_delay_days.desc(),
        ValveReadinessSummary.assembly_date.asc(),
        ValveReadinessSummary.value_cr.desc(),
        ValveReadinessSummary.valve_id.asc(),
        ValveReadinessSummary.id.asc(),
    )
    total, rows = _paginate_scalars(db, query, page=page, page_size=page_size)
    return AssemblyRiskListResponse(
        items=[
            AssemblyRiskItemResponse(
                valve_id=row.valve_id,
                customer=row.customer,
                assembly_date=row.assembly_date,
                expected_completion_date=row.valve_expected_completion_date,
                assembly_delay_days=float(row.otd_delay_days),
                reason=row.risk_reason,
                suggested_action=_assembly_risk_action(row.risk_reason),
                value_cr=float(row.value_cr),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_recommendations(
    planning_run_id: str,
    db: Session,
    *,
    page: int,
    page_size: int,
    sort: str | None,
    direction: str,
    customer: str | None,
    recommendation_type: str | None,
    status_filter: str | None,
) -> RecommendationListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    query = (
        select(Recommendation, Valve.customer)
        .join(
            Valve,
            (Valve.planning_run_id == Recommendation.planning_run_id) & (Valve.valve_id == Recommendation.valve_id),
            isouter=True,
        )
        .join(
            PlannedOperation,
            PlannedOperation.id == Recommendation.planned_operation_id,
            isouter=True,
        )
        .where(Recommendation.planning_run_id == planning_run_id)
    )
    if customer:
        query = query.where(Valve.customer == customer)
    if recommendation_type:
        query = query.where(Recommendation.recommendation_type == recommendation_type)
    if status_filter:
        query = query.where(Recommendation.status == status_filter)
    query = _apply_sort(
        query,
        sort=sort,
        direction=direction,
        mapping={
            "recommendation_type": Recommendation.recommendation_type,
            "status": Recommendation.status,
            "vendor_gain_days": Recommendation.vendor_gain_days,
            "internal_wait_days": Recommendation.internal_wait_days,
            "internal_completion_days": Recommendation.internal_completion_days,
            "assembly_date": Valve.assembly_date,
            "priority_score": PlannedOperation.priority_score,
            "customer": Valve.customer,
            "component": Recommendation.component,
        },
        default=(
            Recommendation.vendor_gain_days.desc(),
            Recommendation.internal_wait_days.desc(),
            Valve.assembly_date.asc(),
            PlannedOperation.priority_score.desc(),
            Recommendation.id.asc(),
        ),
        tie_breakers=(Recommendation.created_at.asc(), Recommendation.id.asc()),
    )
    total, rows = _paginate(db, query, page=page, page_size=page_size)

    return RecommendationListResponse(
        items=[
            RecommendationItemResponse(
                id=row.Recommendation.id,
                planned_operation_id=row.Recommendation.planned_operation_id,
                valve_id=row.Recommendation.valve_id,
                customer=row.customer,
                component_line_no=row.Recommendation.component_line_no,
                component=row.Recommendation.component,
                operation_name=row.Recommendation.operation_name,
                machine_type=row.Recommendation.machine_type,
                recommendation_type=row.Recommendation.recommendation_type,
                recommendation_status=_recommendation_status_for_display(row.Recommendation),
                suggested_machine_type=row.Recommendation.suggested_machine_type,
                suggested_vendor_id=row.Recommendation.suggested_vendor_id,
                suggested_vendor_name=row.Recommendation.suggested_vendor_name,
                internal_wait_days=row.Recommendation.internal_wait_days,
                processing_time_days=row.Recommendation.processing_time_days,
                internal_completion_days=row.Recommendation.internal_completion_days,
                vendor_total_days=row.Recommendation.vendor_total_days,
                vendor_gain_days=row.Recommendation.vendor_gain_days,
                subcontract_batch_candidate_count=row.Recommendation.subcontract_batch_candidate_count,
                batch_subcontract_opportunity_flag=bool(row.Recommendation.batch_subcontract_opportunity_flag),
                reason_codes=_parse_json_array(row.Recommendation.reason_codes_json),
                explanation=row.Recommendation.explanation,
                status=row.Recommendation.status,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_flow_blockers(
    planning_run_id: str,
    db: Session,
    *,
    page: int,
    page_size: int,
    sort: str | None,
    direction: str,
    customer: str | None,
    blocker_type: str | None,
    status_filter: str | None,
) -> FlowBlockerListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    query = (
        select(FlowBlocker, Valve.customer)
        .join(
            Valve,
            (Valve.planning_run_id == FlowBlocker.planning_run_id) & (Valve.valve_id == FlowBlocker.valve_id),
            isouter=True,
        )
        .where(FlowBlocker.planning_run_id == planning_run_id)
    )
    if customer:
        query = query.where(Valve.customer == customer)
    if blocker_type:
        query = query.where(FlowBlocker.blocker_type == blocker_type)
    if status_filter:
        query = query.where(FlowBlocker.severity == status_filter)
    severity_order = case(
        (FlowBlocker.severity == "CRITICAL", 0),
        (FlowBlocker.severity == "WARNING", 1),
        (FlowBlocker.severity == "INFO", 2),
        else_=99,
    )
    query = _apply_sort(
        query,
        sort=sort,
        direction=direction,
        mapping={
            "severity": severity_order,
            "blocker_type": FlowBlocker.blocker_type,
            "customer": Valve.customer,
            "component": FlowBlocker.component,
            "created_at": FlowBlocker.created_at,
        },
        default=(FlowBlocker.created_at.asc(), FlowBlocker.id.asc()),
        tie_breakers=(FlowBlocker.created_at.asc(), FlowBlocker.id.asc()),
    )
    total, rows = _paginate(db, query, page=page, page_size=page_size)

    return FlowBlockerListResponse(
        items=[
            FlowBlockerItemResponse(
                id=row.FlowBlocker.id,
                planned_operation_id=row.FlowBlocker.planned_operation_id,
                valve_id=row.FlowBlocker.valve_id,
                customer=row.customer,
                component_line_no=row.FlowBlocker.component_line_no,
                component=row.FlowBlocker.component,
                operation_name=row.FlowBlocker.operation_name,
                blocker_type=row.FlowBlocker.blocker_type,
                cause=row.FlowBlocker.cause,
                recommended_action=row.FlowBlocker.recommended_action,
                severity=row.FlowBlocker.severity,
                created_at=row.FlowBlocker.created_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def list_vendor_load(
    planning_run_id: str,
    db: Session,
    *,
    page: int,
    page_size: int,
    sort: str | None,
    direction: str,
    status_filter: str | None,
) -> VendorLoadListResponse:
    _ensure_planning_run_exists(planning_run_id, db)

    query = (
        select(VendorLoadSummary, Vendor.capacity_rating, Vendor.reliability, Vendor.comments)
        .join(
            Vendor,
            (Vendor.planning_run_id == VendorLoadSummary.planning_run_id)
            & (Vendor.vendor_id == VendorLoadSummary.vendor_id),
        )
        .where(VendorLoadSummary.planning_run_id == planning_run_id)
    )
    if status_filter:
        query = query.where(VendorLoadSummary.status == status_filter)
    query = _apply_sort(
        query,
        sort=sort,
        direction=direction,
        mapping={
            "vendor_name": VendorLoadSummary.vendor_name,
            "recommended_jobs": VendorLoadSummary.vendor_recommended_jobs,
            "capacity_limit": VendorLoadSummary.max_recommended_jobs_per_horizon,
            "status": VendorLoadSummary.status,
        },
        default=(VendorLoadSummary.vendor_name.asc(), VendorLoadSummary.vendor_id.asc(), VendorLoadSummary.id.asc()),
        tie_breakers=(VendorLoadSummary.vendor_id.asc(), VendorLoadSummary.id.asc()),
    )
    total, rows = _paginate(db, query, page=page, page_size=page_size)

    return VendorLoadListResponse(
        items=[
            VendorLoadItemResponse(
                vendor_id=row.VendorLoadSummary.vendor_id,
                vendor_name=row.VendorLoadSummary.vendor_name,
                primary_process=row.VendorLoadSummary.primary_process,
                vendor_recommended_jobs=row.VendorLoadSummary.vendor_recommended_jobs,
                max_recommended_jobs_per_horizon=row.VendorLoadSummary.max_recommended_jobs_per_horizon,
                selected_vendor_overloaded_flag=bool(row.VendorLoadSummary.selected_vendor_overloaded_flag),
                status=row.VendorLoadSummary.status,
                capacity_rating=row.capacity_rating,
                reliability=row.reliability,
                comments=row.comments,
                limitation_warning=VENDOR_LIMITATION_WARNING,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_throughput_summary(planning_run_id: str, db: Session) -> ThroughputSummaryResponse:
    _ensure_planning_run_exists(planning_run_id, db)
    throughput = db.scalar(
        select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
    )
    if throughput is None:
        return ThroughputSummaryResponse(
            planning_run_id=planning_run_id,
            target_throughput_value_cr=0.0,
            planned_throughput_value_cr=0.0,
            throughput_gap_cr=0.0,
            throughput_risk_flag=False,
        )
    return ThroughputSummaryResponse(
        planning_run_id=planning_run_id,
        target_throughput_value_cr=float(throughput.target_throughput_value_cr),
        planned_throughput_value_cr=float(throughput.planned_throughput_value_cr),
        throughput_gap_cr=float(throughput.throughput_gap_cr),
        throughput_risk_flag=bool(throughput.throughput_risk_flag),
    )


def _ensure_planning_run_exists(planning_run_id: str, db: Session) -> None:
    planning_run = db.get(PlanningRun, planning_run_id)
    if planning_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PLANNING_RUN_NOT_FOUND", "message": f"PlanningRun {planning_run_id} was not found."},
        )


def _apply_sort(
    query: Select,
    *,
    sort: str | None,
    direction: str,
    mapping: dict[str, object],
    default,
    tie_breakers: tuple[object, ...] = (),
) -> Select:
    if sort is None or sort not in mapping:
        if isinstance(default, tuple):
            return query.order_by(*default)
        return query.order_by(default)
    column = mapping[sort]
    if direction.lower() == "desc":
        return query.order_by(column.desc(), *tie_breakers)
    return query.order_by(column.asc(), *tie_breakers)


def _paginate(db: Session, query: Select, *, page: int, page_size: int):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = list(db.execute(query.offset((page - 1) * page_size).limit(page_size)))
    return total, rows


def _paginate_scalars(db: Session, query: Select, *, page: int, page_size: int):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = list(db.scalars(query.offset((page - 1) * page_size).limit(page_size)))
    return total, rows


def _parse_json_array(value: str | None) -> list[str]:
    if value is None:
        return []
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def _machine_load_summary_response(row: MachineLoadSummary) -> MachineLoadSummaryResponse:
    return MachineLoadSummaryResponse(
        machine_type=row.machine_type,
        total_operation_hours=float(row.total_operation_hours),
        capacity_hours_per_day=float(row.capacity_hours_per_day),
        load_days=float(row.load_days),
        buffer_days=float(row.buffer_days),
        overload_flag=bool(row.overload_flag),
        overload_days=float(row.overload_days),
        spare_capacity_days=float(row.spare_capacity_days),
        underutilized_flag=bool(row.underutilized_flag),
        batch_risk_flag=bool(row.batch_risk_flag),
        status=row.status,
        queue_approximation_warning=row.queue_approximation_warning,
    )


def _valve_readiness_response(row: ValveReadinessSummary) -> ValveReadinessItemResponse:
    return ValveReadinessItemResponse(
        valve_id=row.valve_id,
        customer=row.customer,
        assembly_date=row.assembly_date,
        dispatch_date=row.dispatch_date,
        value_cr=float(row.value_cr),
        total_components=row.total_components,
        ready_components=row.ready_components,
        required_components=row.required_components,
        ready_required_count=row.ready_required_count,
        pending_required_count=row.pending_required_count,
        full_kit_flag=bool(row.full_kit_flag),
        near_ready_flag=bool(row.near_ready_flag),
        valve_expected_completion_date=row.valve_expected_completion_date,
        otd_delay_days=float(row.otd_delay_days),
        otd_risk_flag=bool(row.otd_risk_flag),
        readiness_status=row.readiness_status,
        risk_reason=row.risk_reason,
        valve_flow_gap_days=row.valve_flow_gap_days,
        valve_flow_imbalance_flag=bool(row.valve_flow_imbalance_flag),
    )


def _component_status_display(*, row: ComponentStatus, blocker_types: list[str]) -> str:
    if blocker_types:
        return "BLOCKED"
    if bool(row.fabrication_complete) or not bool(row.fabrication_required):
        return "READY"
    return "PENDING"


def _assembly_risk_action(risk_reason: str | None) -> str:
    if risk_reason == "Missing component":
        return "Expedite missing components and rebalance the valve before assembly."
    if risk_reason == "Data issue":
        return "Resolve missing or invalid planning data before committing assembly."
    return "Review queue, machine, and vendor constraints to recover the assembly date."


def _recommendation_status_for_display(row: Recommendation) -> str | None:
    if row.recommendation_type == "BATCH_SUBCONTRACT_OPPORTUNITY":
        return "SUBCONTRACT"
    return row.recommendation_type
