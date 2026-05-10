from pathlib import Path

from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_api_contract_exposes_filters_used_by_frontend() -> None:
    openapi = create_app().openapi()

    incoming_params = _parameter_names(
        openapi,
        "/api/v1/planning-runs/{planning_run_id}/incoming-load",
    )
    assert {
        "page",
        "page_size",
        "sort",
        "direction",
        "customer",
        "valve_type",
        "machine_type",
        "date_confidence",
        "availability_from",
        "availability_to",
    }.issubset(incoming_params)

    queue_params = _parameter_names(
        openapi,
        "/api/v1/planning-runs/{planning_run_id}/machine-load/{machine_type}/queue",
    )
    assert {
        "page",
        "page_size",
        "sort",
        "direction",
        "customer",
        "status",
        "date_confidence",
        "kit",
        "recommendation",
    }.issubset(queue_params)


def test_frontend_wires_incoming_load_and_planner_action_contracts() -> None:
    api_source = (REPO_ROOT / "frontend" / "src" / "api" / "planningRuns.ts").read_text(encoding="utf-8")
    app_source = (REPO_ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "export async function fetchIncomingLoad" in api_source
    assert "/incoming-load?" in api_source
    assert "valve_type?: string" in api_source
    assert "machine_type?: string" in api_source
    assert "date_confidence?: string" in api_source
    assert 'entity_type: "RECOMMENDATION" | "OPERATION" | "VALVE" | "MACHINE" | "VENDOR"' in api_source

    assert '"Incoming Load"' in app_source
    assert "IncomingLoadWorkspace" in app_source
    assert "fetchIncomingLoad(planningRun.id, compactFilters(filters))" in app_source
    assert "submitGeneralPlannerAction" in app_source


def _parameter_names(openapi: dict[str, object], path: str) -> set[str]:
    paths = openapi["paths"]
    assert isinstance(paths, dict)
    operation = paths[path]["get"]  # type: ignore[index]
    parameters = operation["parameters"]  # type: ignore[index]
    return {parameter["name"] for parameter in parameters}
