from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.canonical import ComponentStatus, Machine, RoutingOperation, Valve, Vendor
from app.models.planning_run import PlanningRun
from app.models.upload import UploadBatch
from app.services.canonical_promotion import PromotionError, promote_upload_to_canonical
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "canonical_promotion.sqlite3"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", upload_dir.as_posix())
    monkeypatch.setenv("EXPORT_DIR", export_dir.as_posix())
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()


def test_promote_valid_upload_creates_canonical_records_and_recalculates_derived_fields(client: TestClient) -> None:
    upload_id = _upload_workbook(client, _workbook_with_untrusted_derived_fields())
    planning_run_id = _create_planning_run(upload_id)

    session_factory = create_session_factory()
    with session_factory() as session:
        result = promote_upload_to_canonical(upload_batch_id=upload_id, planning_run_id=planning_run_id, db=session)

    assert result.valves == 1
    assert result.component_statuses == 1
    assert result.routing_operations == 1
    assert result.machines == 1
    assert result.vendors == 1

    with session_factory() as session:
        upload = session.get(UploadBatch, upload_id)
        valve = session.scalar(select(Valve).where(Valve.planning_run_id == planning_run_id))
        component = session.scalar(select(ComponentStatus).where(ComponentStatus.planning_run_id == planning_run_id))
        routing = session.scalar(select(RoutingOperation).where(RoutingOperation.planning_run_id == planning_run_id))
        machine = session.scalar(select(Machine).where(Machine.planning_run_id == planning_run_id))
        vendor = session.scalar(select(Vendor).where(Vendor.planning_run_id == planning_run_id))

    assert upload is not None
    assert upload.status == "PROMOTED"
    assert valve is not None
    assert valve.valve_id == "V-100"
    assert component is not None
    assert component.component_line_no == 1
    assert component.ready_date_type == "EXPECTED"
    assert routing is not None
    assert routing.subcontract_allowed == 1
    assert machine is not None
    assert machine.effective_hours_day == pytest.approx(12.8)
    assert vendor is not None
    assert vendor.effective_lead_days == pytest.approx(4)


def test_promote_allows_warning_only_uploads(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Vendor_Master"][1][5] = "N"
    upload_id = _upload_workbook(client, workbook_bytes(sheets=sheets))
    planning_run_id = _create_planning_run(upload_id)

    session_factory = create_session_factory()
    with session_factory() as session:
        result = promote_upload_to_canonical(upload_batch_id=upload_id, planning_run_id=planning_run_id, db=session)

    assert result.vendors == 1

    with session_factory() as session:
        vendor = session.scalar(select(Vendor).where(Vendor.planning_run_id == planning_run_id))
        upload = session.get(UploadBatch, upload_id)

    assert vendor is not None
    assert vendor.approved == 0
    assert upload is not None
    assert upload.status == "PROMOTED"
    assert upload.validation_warning_count == 1


def test_promote_rejects_upload_with_blocking_validation_issues(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    del sheets["Machine_Master"]
    upload_id = _upload_workbook(client, workbook_bytes(sheets=sheets))
    planning_run_id = _create_planning_run(upload_id)

    session_factory = create_session_factory()
    with session_factory() as session:
        with pytest.raises(PromotionError, match="VALIDATION_BLOCKED"):
            promote_upload_to_canonical(upload_batch_id=upload_id, planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        valve_count = session.scalar(select(func.count()).select_from(Valve).where(Valve.planning_run_id == planning_run_id))
        upload = session.get(UploadBatch, upload_id)

    assert valve_count == 0
    assert upload is not None
    assert upload.status == "VALIDATION_FAILED"


def test_promote_requires_planning_run_to_match_upload(client: TestClient) -> None:
    upload_id = _upload_workbook(client, workbook_bytes())
    other_upload_id = _upload_workbook(client, workbook_bytes())
    planning_run_id = _create_planning_run(other_upload_id)

    session_factory = create_session_factory()
    with session_factory() as session:
        with pytest.raises(PromotionError, match="PLANNING_RUN_UPLOAD_MISMATCH"):
            promote_upload_to_canonical(upload_batch_id=upload_id, planning_run_id=planning_run_id, db=session)


def test_promote_rejects_second_promotion_for_same_planning_run(client: TestClient) -> None:
    upload_id = _upload_workbook(client, workbook_bytes())
    planning_run_id = _create_planning_run(upload_id)

    session_factory = create_session_factory()
    with session_factory() as session:
        promote_upload_to_canonical(upload_batch_id=upload_id, planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        with pytest.raises(PromotionError, match="CANONICAL_ALREADY_PROMOTED"):
            promote_upload_to_canonical(upload_batch_id=upload_id, planning_run_id=planning_run_id, db=session)


def test_promote_preserves_generated_component_line_numbers_for_repeated_components(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Component_Status"].append(["V-100", "Body", 1, "Y", "N", "2026-04-25", "Y"])
    upload_id = _upload_workbook(client, workbook_bytes(sheets=sheets))
    planning_run_id = _create_planning_run(upload_id)

    session_factory = create_session_factory()
    with session_factory() as session:
        promote_upload_to_canonical(upload_batch_id=upload_id, planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        components = list(
            session.scalars(
                select(ComponentStatus)
                .where(ComponentStatus.planning_run_id == planning_run_id)
                .order_by(ComponentStatus.component_line_no)
            )
        )

    assert [component.component_line_no for component in components] == [1, 2]
    assert [component.component for component in components] == ["Body", "Body"]


def _upload_workbook(client: TestClient, content: bytes) -> str:
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("plan.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 201
    return response.json()["id"]


def _create_planning_run(upload_id: str) -> str:
    planning_run_id = f"run-{upload_id}"
    session_factory = create_session_factory()
    with session_factory() as session:
        session.add(
            PlanningRun(
                id=planning_run_id,
                upload_batch_id=upload_id,
                planning_start_date="2026-04-21",
                planning_horizon_days=7,
                status="CREATED",
                created_by_user_id=DEV_USER_ID,
                created_at="2026-04-21T00:00:00Z",
            )
        )
        session.commit()
    return planning_run_id


def _workbook_with_untrusted_derived_fields() -> bytes:
    sheets = minimal_workbook_rows()
    sheets["Machine_Master"][0].insert(5, "Effective_Hours_Day")
    sheets["Machine_Master"][1].insert(5, 99)
    sheets["Vendor_Master"][0].insert(5, "Effective_Lead_Days")
    sheets["Vendor_Master"][1].insert(5, 99)
    return workbook_bytes(sheets=sheets)
