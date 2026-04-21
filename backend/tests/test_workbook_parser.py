from app.imports.workbook import REQUIRED_SHEETS, normalize_header, parse_workbook
from tests.workbook_fixtures import workbook_bytes


def test_normalize_header_maps_common_variants_to_canonical_names() -> None:
    assert normalize_header("Valve_ID") == "valve_id"
    assert normalize_header(" valve   id ") == "valve_id"
    assert normalize_header("Valve-ID") == "valve_id"
    assert normalize_header("Value (Cr)") == "value_cr"
    assert normalize_header("Efficiency %") == "efficiency_percent"


def test_parse_workbook_reads_required_sheets_and_ignores_extra_sheet() -> None:
    parsed_rows = parse_workbook(workbook_bytes(include_extra_sheet=True))

    assert {row.sheet_name for row in parsed_rows} == set(REQUIRED_SHEETS)
    assert len(parsed_rows) == 5
    assert all(row.row_number == 2 for row in parsed_rows)


def test_parse_workbook_stores_normalized_payloads() -> None:
    parsed_rows = parse_workbook(workbook_bytes())
    valve_row = next(row for row in parsed_rows if row.sheet_name == "Valve_Plan")
    machine_row = next(row for row in parsed_rows if row.sheet_name == "Machine_Master")

    assert valve_row.payload["valve_id"] == "V-100"
    assert valve_row.payload["order_id"] == "O-100"
    assert valve_row.payload["value_cr"] == 1.25
    assert machine_row.payload["efficiency_percent"] == 80
