from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.core.ids import new_uuid
from app.imports.workbook import ParsedWorkbook, ParsedWorkbookRow, hash_payload
from app.models.upload import ImportStagingRow, ImportValidationIssue

Severity = Literal["BLOCKING", "WARNING"]
FieldKind = Literal["text", "date", "number", "integer", "boolean", "enum"]

REQUIRED_COLUMNS_BY_SHEET: dict[str, tuple[str, ...]] = {
    "Valve_Plan": ("valve_id", "order_id", "customer", "dispatch_date", "assembly_date", "value_cr"),
    "Component_Status": (
        "valve_id",
        "component",
        "qty",
        "fabrication_required",
        "fabrication_complete",
        "expected_ready_date",
        "critical",
    ),
    "Routing_Master": (
        "component",
        "operation_no",
        "operation_name",
        "machine_type",
        "std_total_hrs",
        "subcontract_allowed",
    ),
    "Machine_Master": (
        "machine_id",
        "machine_type",
        "hours_per_day",
        "efficiency_percent",
        "buffer_days",
        "active",
    ),
    "Vendor_Master": (
        "vendor_id",
        "vendor_name",
        "primary_process",
        "turnaround_days",
        "transport_days_total",
        "approved",
    ),
}

VALID_READY_DATE_TYPES = {"CONFIRMED", "EXPECTED", "TENTATIVE"}


@dataclass(frozen=True)
class FieldRule:
    kind: FieldKind
    required: bool = False
    positive: bool = False
    nonnegative: bool = False
    max_value: float | None = None
    values: frozenset[str] | None = None


FIELD_RULES_BY_SHEET: dict[str, dict[str, FieldRule]] = {
    "Valve_Plan": {
        "valve_id": FieldRule("text", required=True),
        "order_id": FieldRule("text", required=True),
        "customer": FieldRule("text", required=True),
        "dispatch_date": FieldRule("date", required=True),
        "assembly_date": FieldRule("date", required=True),
        "value_cr": FieldRule("number", required=True, nonnegative=True),
    },
    "Component_Status": {
        "valve_id": FieldRule("text", required=True),
        "component_line_no": FieldRule("integer", positive=True),
        "component": FieldRule("text", required=True),
        "qty": FieldRule("number", required=True, positive=True),
        "fabrication_required": FieldRule("boolean", required=True),
        "fabrication_complete": FieldRule("boolean", required=True),
        "expected_ready_date": FieldRule("date"),
        "critical": FieldRule("boolean", required=True),
        "expected_from_fabrication": FieldRule("date"),
        "priority_eligible": FieldRule("boolean"),
        "ready_date_type": FieldRule("enum", values=frozenset(VALID_READY_DATE_TYPES)),
    },
    "Routing_Master": {
        "component": FieldRule("text", required=True),
        "operation_no": FieldRule("integer", required=True, positive=True),
        "operation_name": FieldRule("text", required=True),
        "machine_type": FieldRule("text", required=True),
        "alt_machine": FieldRule("text"),
        "std_setup_hrs": FieldRule("number", nonnegative=True),
        "std_run_hrs": FieldRule("number", nonnegative=True),
        "std_total_hrs": FieldRule("number", required=True, positive=True),
        "subcontract_allowed": FieldRule("boolean", required=True),
        "vendor_process": FieldRule("text"),
    },
    "Machine_Master": {
        "machine_id": FieldRule("text", required=True),
        "machine_type": FieldRule("text", required=True),
        "hours_per_day": FieldRule("number", required=True, positive=True),
        "efficiency_percent": FieldRule("number", required=True, positive=True, max_value=100),
        "buffer_days": FieldRule("number", required=True, positive=True),
        "active": FieldRule("boolean", required=True),
    },
    "Vendor_Master": {
        "vendor_id": FieldRule("text", required=True),
        "vendor_name": FieldRule("text", required=True),
        "primary_process": FieldRule("text", required=True),
        "turnaround_days": FieldRule("number", required=True, nonnegative=True),
        "transport_days_total": FieldRule("number", required=True, nonnegative=True),
        "approved": FieldRule("boolean", required=True),
    },
}


def with_generated_component_line_numbers(parsed_workbook: ParsedWorkbook) -> ParsedWorkbook:
    row_counts_by_valve: dict[str, int] = defaultdict(int)
    prepared_rows: list[ParsedWorkbookRow] = []

    for row in parsed_workbook.rows:
        if row.sheet_name != "Component_Status":
            prepared_rows.append(row)
            continue

        payload = dict(row.payload)
        valve_id = _clean_text(payload.get("valve_id"))
        if valve_id:
            row_counts_by_valve[valve_id] += 1
            if _is_blank(payload.get("component_line_no")):
                payload["component_line_no"] = row_counts_by_valve[valve_id]

        prepared_rows.append(
            ParsedWorkbookRow(
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                payload=payload,
                row_hash=hash_payload(payload),
            )
        )

    return ParsedWorkbook(
        workbook_sheet_names=parsed_workbook.workbook_sheet_names,
        headers_by_sheet=parsed_workbook.headers_by_sheet,
        rows=prepared_rows,
    )


def validate_import(
    upload_batch_id: str,
    parsed_workbook: ParsedWorkbook,
    staging_rows: list[ImportStagingRow],
    created_at: str,
) -> list[ImportValidationIssue]:
    staging_id_by_source = {(row.sheet_name, row.row_number): row.id for row in staging_rows}
    issue_builder = _IssueBuilder(upload_batch_id, staging_id_by_source, created_at)

    _validate_duplicate_columns(parsed_workbook, issue_builder)
    _validate_required_sheets_and_columns(parsed_workbook, issue_builder)
    _validate_required_sheet_row_presence(parsed_workbook, issue_builder)
    _validate_row_values(parsed_workbook, issue_builder)
    _validate_component_expected_ready_dates(parsed_workbook, issue_builder)
    _validate_component_line_uniqueness(parsed_workbook, issue_builder)
    _validate_canonical_unique_keys(parsed_workbook, issue_builder)
    _validate_valves_have_component_rows(parsed_workbook, issue_builder)
    _validate_references(parsed_workbook, issue_builder)

    return issue_builder.issues


def count_issues(issues: list[ImportValidationIssue]) -> tuple[int, int]:
    blocking = sum(1 for issue in issues if issue.severity == "BLOCKING")
    warning = sum(1 for issue in issues if issue.severity == "WARNING")
    return blocking, warning


class _IssueBuilder:
    def __init__(self, upload_batch_id: str, staging_id_by_source: dict[tuple[str, int], str], created_at: str) -> None:
        self.upload_batch_id = upload_batch_id
        self.staging_id_by_source = staging_id_by_source
        self.created_at = created_at
        self.issues: list[ImportValidationIssue] = []

    def add(
        self,
        *,
        severity: Severity,
        issue_code: str,
        message: str,
        sheet_name: str | None = None,
        row_number: int | None = None,
        field_name: str | None = None,
    ) -> None:
        staging_row_id = None
        if sheet_name is not None and row_number is not None:
            staging_row_id = self.staging_id_by_source.get((sheet_name, row_number))

        self.issues.append(
            ImportValidationIssue(
                id=new_uuid(),
                upload_batch_id=self.upload_batch_id,
                staging_row_id=staging_row_id,
                sheet_name=sheet_name,
                row_number=row_number,
                severity=severity,
                issue_code=issue_code,
                message=message,
                field_name=field_name,
                created_at=self.created_at,
            )
        )


def _validate_required_sheets_and_columns(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    present_sheets = set(parsed_workbook.workbook_sheet_names)
    for sheet_name, required_columns in REQUIRED_COLUMNS_BY_SHEET.items():
        if sheet_name not in present_sheets:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="MISSING_SHEET",
                message=f"Required sheet {sheet_name} is missing.",
                sheet_name=sheet_name,
            )
            continue

        headers = set(parsed_workbook.headers_by_sheet.get(sheet_name, ()))
        for column in required_columns:
            if column not in headers:
                issue_builder.add(
                    severity="BLOCKING",
                    issue_code="MISSING_COLUMN",
                    message=f"Required column {column} is missing from {sheet_name}.",
                    sheet_name=sheet_name,
                    field_name=column,
                )


def _validate_duplicate_columns(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    for sheet_name, headers in parsed_workbook.headers_by_sheet.items():
        occurrences_by_header: dict[str, int] = defaultdict(int)
        for header in headers:
            occurrences_by_header[header] += 1

        for header, occurrence_count in occurrences_by_header.items():
            if occurrence_count <= 1:
                continue

            issue_builder.add(
                severity="BLOCKING",
                issue_code="DUPLICATE_COLUMN",
                message=f"Column {header} appears {occurrence_count} times after header normalization.",
                sheet_name=sheet_name,
                field_name=header,
            )


def _validate_required_sheet_row_presence(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    present_sheets = set(parsed_workbook.workbook_sheet_names)
    rows_by_sheet = _rows_by_sheet(parsed_workbook.rows)

    for sheet_name in REQUIRED_COLUMNS_BY_SHEET:
        if sheet_name in present_sheets and not rows_by_sheet[sheet_name]:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="EMPTY_SHEET",
                message=f"Required sheet {sheet_name} must include at least one data row.",
                sheet_name=sheet_name,
            )


def _validate_component_expected_ready_dates(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    for row in parsed_workbook.rows:
        if row.sheet_name != "Component_Status":
            continue

        if not _is_blank(row.payload.get("expected_ready_date")):
            continue

        fabrication_required = _parse_bool(row.payload.get("fabrication_required"))
        fabrication_complete = _parse_bool(row.payload.get("fabrication_complete"))
        if fabrication_required is None or fabrication_complete is None:
            continue

        current_ready_flag = (not fabrication_required) or fabrication_complete
        if current_ready_flag:
            issue_builder.add(
                severity="WARNING",
                issue_code="MISSING_EXPECTED_READY_DATE",
                message="Ready component has no expected_ready_date; planning will use planning_start_date.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name="expected_ready_date",
            )
            continue

        issue_builder.add(
            severity="BLOCKING",
            issue_code="MISSING_EXPECTED_READY_DATE",
            message="Not-ready component must include expected_ready_date.",
            sheet_name=row.sheet_name,
            row_number=row.row_number,
            field_name="expected_ready_date",
        )


def _validate_row_values(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    headers_by_sheet = {sheet_name: set(headers) for sheet_name, headers in parsed_workbook.headers_by_sheet.items()}
    for row in parsed_workbook.rows:
        rules = FIELD_RULES_BY_SHEET.get(row.sheet_name, {})
        headers = headers_by_sheet.get(row.sheet_name, set())
        for field_name, rule in rules.items():
            if field_name not in headers and field_name not in row.payload:
                continue

            value = row.payload.get(field_name)
            if _is_blank(value):
                if rule.required:
                    issue_builder.add(
                        severity="BLOCKING",
                        issue_code="MISSING_REQUIRED_VALUE",
                        message=f"{field_name} is required.",
                        sheet_name=row.sheet_name,
                        row_number=row.row_number,
                        field_name=field_name,
                    )
                continue

            _validate_field_value(row, field_name, value, rule, issue_builder)


def _validate_field_value(
    row: ParsedWorkbookRow,
    field_name: str,
    value: Any,
    rule: FieldRule,
    issue_builder: _IssueBuilder,
) -> None:
    parsed_number: float | None = None
    if rule.kind == "text":
        if not _clean_text(value):
            issue_builder.add(
                severity="BLOCKING",
                issue_code="MISSING_REQUIRED_VALUE",
                message=f"{field_name} must contain text.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name=field_name,
            )
        return

    if rule.kind == "date":
        if _parse_date(value) is None:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="INVALID_DATE",
                message=f"{field_name} must be a valid ISO date.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name=field_name,
            )
        return

    if rule.kind == "boolean":
        if _parse_bool(value) is None:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="INVALID_BOOLEAN",
                message=f"{field_name} must be Y/N, true/false, or 1/0.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name=field_name,
            )
        return

    if rule.kind == "integer":
        parsed_integer = _parse_int(value)
        if parsed_integer is None:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="INVALID_INTEGER",
                message=f"{field_name} must be an integer.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name=field_name,
            )
            return
        parsed_number = float(parsed_integer)

    if rule.kind == "number":
        parsed_number = _parse_number(value)
        if parsed_number is None:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="INVALID_NUMBER",
                message=f"{field_name} must be numeric.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name=field_name,
            )
            return

    if rule.kind == "enum":
        if rule.values is not None and _clean_text(value).upper() not in rule.values:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="INVALID_ENUM",
                message=f"{field_name} must be one of {', '.join(sorted(rule.values))}.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name=field_name,
            )
        return

    if parsed_number is None:
        return

    if rule.positive and parsed_number <= 0:
        issue_builder.add(
            severity="BLOCKING",
            issue_code="NONPOSITIVE_NUMBER",
            message=f"{field_name} must be greater than zero.",
            sheet_name=row.sheet_name,
            row_number=row.row_number,
            field_name=field_name,
        )
    if rule.nonnegative and parsed_number < 0:
        issue_builder.add(
            severity="BLOCKING",
            issue_code="NEGATIVE_NUMBER",
            message=f"{field_name} must be zero or greater.",
            sheet_name=row.sheet_name,
            row_number=row.row_number,
            field_name=field_name,
        )
    if rule.max_value is not None and parsed_number > rule.max_value:
        issue_builder.add(
            severity="BLOCKING",
            issue_code="NUMBER_TOO_HIGH",
            message=f"{field_name} must be less than or equal to {rule.max_value:g}.",
            sheet_name=row.sheet_name,
            row_number=row.row_number,
            field_name=field_name,
        )


def _validate_component_line_uniqueness(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    rows_by_key: dict[tuple[str, int], list[ParsedWorkbookRow]] = defaultdict(list)
    for row in parsed_workbook.rows:
        if row.sheet_name != "Component_Status":
            continue

        valve_id = _clean_text(row.payload.get("valve_id"))
        component_line_no = _parse_int(row.payload.get("component_line_no"))
        if not valve_id or component_line_no is None:
            continue

        rows_by_key[(valve_id, component_line_no)].append(row)

    for (valve_id, component_line_no), rows in rows_by_key.items():
        if len(rows) <= 1:
            continue

        for row in rows:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="DUPLICATE_COMPONENT_LINE_NO",
                message=f"Valve {valve_id} has duplicate component_line_no {component_line_no}.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name="component_line_no",
            )


def _validate_valves_have_component_rows(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    rows_by_sheet = _rows_by_sheet(parsed_workbook.rows)
    component_valve_ids = {
        _clean_text(row.payload.get("valve_id"))
        for row in rows_by_sheet["Component_Status"]
        if _clean_text(row.payload.get("valve_id"))
    }

    for row in rows_by_sheet["Valve_Plan"]:
        valve_id = _clean_text(row.payload.get("valve_id"))
        if not valve_id or valve_id in component_valve_ids:
            continue

        issue_builder.add(
            severity="BLOCKING",
            issue_code="MISSING_COMPONENT_STATUS",
            message=f"Valve_ID {valve_id} has no Component_Status rows.",
            sheet_name=row.sheet_name,
            row_number=row.row_number,
            field_name="valve_id",
        )


def _validate_canonical_unique_keys(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    rows_by_sheet = _rows_by_sheet(parsed_workbook.rows)
    _validate_unique_key(
        rows_by_sheet["Valve_Plan"],
        ("valve_id",),
        issue_code="DUPLICATE_VALVE_ID",
        field_name="valve_id",
        label="Valve_ID",
        issue_builder=issue_builder,
    )
    _validate_unique_key(
        rows_by_sheet["Routing_Master"],
        ("component", "operation_no"),
        issue_code="DUPLICATE_ROUTING_OPERATION",
        field_name="operation_no",
        label="Component + Operation_No",
        issue_builder=issue_builder,
    )
    _validate_unique_key(
        rows_by_sheet["Machine_Master"],
        ("machine_id",),
        issue_code="DUPLICATE_MACHINE_ID",
        field_name="machine_id",
        label="Machine_ID",
        issue_builder=issue_builder,
    )
    _validate_unique_key(
        rows_by_sheet["Vendor_Master"],
        ("vendor_id",),
        issue_code="DUPLICATE_VENDOR_ID",
        field_name="vendor_id",
        label="Vendor_ID",
        issue_builder=issue_builder,
    )


def _validate_unique_key(
    rows: list[ParsedWorkbookRow],
    fields: tuple[str, ...],
    *,
    issue_code: str,
    field_name: str,
    label: str,
    issue_builder: _IssueBuilder,
) -> None:
    rows_by_key: dict[tuple[Any, ...], list[ParsedWorkbookRow]] = defaultdict(list)
    for row in rows:
        key = _key_for_row(row, fields)
        if key is None:
            continue
        rows_by_key[key].append(row)

    for key, duplicate_rows in rows_by_key.items():
        if len(duplicate_rows) <= 1:
            continue

        key_text = " + ".join(str(part) for part in key)
        for row in duplicate_rows:
            issue_builder.add(
                severity="BLOCKING",
                issue_code=issue_code,
                message=f"Duplicate {label} value {key_text}.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name=field_name,
            )


def _key_for_row(row: ParsedWorkbookRow, fields: tuple[str, ...]) -> tuple[Any, ...] | None:
    key_parts: list[Any] = []
    for field_name in fields:
        if field_name == "operation_no":
            value = _parse_int(row.payload.get(field_name))
        else:
            value = _clean_text(row.payload.get(field_name))

        if value is None or value == "":
            return None
        key_parts.append(value)
    return tuple(key_parts)


def _validate_references(parsed_workbook: ParsedWorkbook, issue_builder: _IssueBuilder) -> None:
    rows_by_sheet = _rows_by_sheet(parsed_workbook.rows)
    valve_ids = {_clean_text(row.payload.get("valve_id")) for row in rows_by_sheet["Valve_Plan"]}
    routing_components = {_clean_text(row.payload.get("component")) for row in rows_by_sheet["Routing_Master"]}
    machine_types = {_clean_text(row.payload.get("machine_type")) for row in rows_by_sheet["Machine_Master"]}
    approved_vendor_processes = {
        _clean_text(row.payload.get("primary_process"))
        for row in rows_by_sheet["Vendor_Master"]
        if _parse_bool(row.payload.get("approved")) is True
    }
    valve_ids.discard("")
    routing_components.discard("")
    machine_types.discard("")
    approved_vendor_processes.discard("")

    for row in rows_by_sheet["Component_Status"]:
        valve_id = _clean_text(row.payload.get("valve_id"))
        if valve_id and valve_id not in valve_ids:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="UNKNOWN_VALVE_ID",
                message=f"Valve_ID {valve_id} does not exist in Valve_Plan.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name="valve_id",
            )

        component = _clean_text(row.payload.get("component"))
        if component and component not in routing_components:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="MISSING_ROUTING",
                message=f"Component {component} does not exist in Routing_Master.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name="component",
            )

    for row in rows_by_sheet["Routing_Master"]:
        machine_type = _clean_text(row.payload.get("machine_type"))
        if machine_type and machine_type not in machine_types:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="UNKNOWN_MACHINE_TYPE",
                message=f"Machine_Type {machine_type} does not exist in Machine_Master.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name="machine_type",
            )

        alt_machine = _clean_text(row.payload.get("alt_machine"))
        if alt_machine and alt_machine not in machine_types:
            issue_builder.add(
                severity="BLOCKING",
                issue_code="UNKNOWN_ALT_MACHINE",
                message=f"Alt_Machine {alt_machine} does not exist in Machine_Master.",
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                field_name="alt_machine",
            )

        if _parse_bool(row.payload.get("subcontract_allowed")) is True:
            vendor_process = _clean_text(row.payload.get("vendor_process")) or machine_type
            if vendor_process and vendor_process not in approved_vendor_processes:
                issue_builder.add(
                    severity="WARNING",
                    issue_code="NO_APPROVED_VENDOR",
                    message=f"No approved vendor exists for process {vendor_process}.",
                    sheet_name=row.sheet_name,
                    row_number=row.row_number,
                    field_name="vendor_process",
                )


def _rows_by_sheet(rows: list[ParsedWorkbookRow]) -> dict[str, list[ParsedWorkbookRow]]:
    rows_by_sheet: dict[str, list[ParsedWorkbookRow]] = defaultdict(list)
    for row in rows:
        rows_by_sheet[row.sheet_name].append(row)
    return rows_by_sheet


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _parse_int(value: Any) -> int | None:
    number = _parse_number(value)
    if number is None or number % 1 != 0:
        return None
    return int(number)


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"y", "yes", "true", "1"}:
            return True
        if normalized in {"n", "no", "false", "0"}:
            return False
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None
