import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

function createJsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  };
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows a validation placeholder before any workbook has been uploaded", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Upload a workbook to review blocking errors and warnings.")).toBeInTheDocument();
    });

    expect(screen.queryByText("No blocking errors.")).not.toBeInTheDocument();
    expect(screen.queryByText("No warnings.")).not.toBeInTheDocument();
  });

  it("renders the upload workspace and successful validation state", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.endsWith("/api/v1/uploads")) {
        return createJsonResponse({
          id: "upload-1",
          original_filename: "plan.xlsx",
          stored_filename: "plan.xlsx",
          file_hash: "abc123",
          file_size_bytes: 4096,
          uploaded_by_user_id: "user-1",
          uploaded_at: "2026-04-30T06:00:00.000000Z",
          status: "VALIDATED",
          validation_error_count: 0,
          validation_warning_count: 1,
          artifact: {
            id: "artifact-1",
            upload_batch_id: "upload-1",
            storage_path: "data/uploads/upload-1/plan.xlsx",
            mime_type:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            created_at: "2026-04-30T06:00:00.000000Z",
          },
        });
      }

      if (url.endsWith("/api/v1/uploads/upload-1/validation-issues")) {
        return createJsonResponse({
          upload_batch_id: "upload-1",
          summary: { blocking: 0, warning: 1, total: 1 },
          issues: [
            {
              id: "issue-1",
              upload_batch_id: "upload-1",
              staging_row_id: "row-1",
              sheet_name: "Component_Status",
              row_number: 4,
              severity: "WARNING",
              issue_code: "TENTATIVE_DATE",
              message: "Expected ready date is tentative and should be reviewed.",
              field_name: "Expected_Ready_Date",
              created_at: "2026-04-30T06:00:00.000000Z",
            },
          ],
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    const fileInput = screen.getByLabelText("Upload workbook");
    fireEvent.change(fileInput, {
      target: {
        files: [
          new File(["workbook"], "plan.xlsx", {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload workbook" }));

    await waitFor(() => {
      expect(screen.getByText("Upload validated. Ready to create planning run.")).toBeInTheDocument();
    });

    expect(screen.getByLabelText("Warnings")).toBeInTheDocument();
    expect(screen.getByText("No blocking errors.")).toBeInTheDocument();
    expect(screen.getByText("Expected ready date is tentative and should be reviewed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Planning run setup next" })).toBeEnabled();
  });

  it("disables planning-run creation when blocking errors exist", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.endsWith("/api/v1/uploads")) {
        return createJsonResponse({
          id: "upload-2",
          original_filename: "broken.xlsx",
          stored_filename: "broken.xlsx",
          file_hash: "def456",
          file_size_bytes: 2048,
          uploaded_by_user_id: "user-1",
          uploaded_at: "2026-04-30T06:10:00.000000Z",
          status: "VALIDATION_FAILED",
          validation_error_count: 1,
          validation_warning_count: 1,
          artifact: {
            id: "artifact-2",
            upload_batch_id: "upload-2",
            storage_path: "data/uploads/upload-2/broken.xlsx",
            mime_type:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            created_at: "2026-04-30T06:10:00.000000Z",
          },
        });
      }

      if (url.endsWith("/api/v1/uploads/upload-2/validation-issues")) {
        return createJsonResponse({
          upload_batch_id: "upload-2",
          summary: { blocking: 1, warning: 1, total: 2 },
          issues: [
            {
              id: "issue-2",
              upload_batch_id: "upload-2",
              staging_row_id: "row-2",
              sheet_name: "Machine_Master",
              row_number: 5,
              severity: "BLOCKING",
              issue_code: "MISSING_MACHINE_TYPE",
              message: "Machine_Type is required.",
              field_name: "Machine_Type",
              created_at: "2026-04-30T06:10:00.000000Z",
            },
            {
              id: "issue-3",
              upload_batch_id: "upload-2",
              staging_row_id: "row-3",
              sheet_name: "Vendor_Master",
              row_number: 2,
              severity: "WARNING",
              issue_code: "VENDOR_REVIEW",
              message: "Vendor lead time should be reviewed.",
              field_name: "Turnaround_Days",
              created_at: "2026-04-30T06:10:01.000000Z",
            },
          ],
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const fileInput = screen.getByLabelText("Upload workbook");
    fireEvent.change(fileInput, {
      target: {
        files: [
          new File(["workbook"], "broken.xlsx", {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload workbook" }));

    await waitFor(() => {
      expect(
        screen.getByText("Upload has blocking errors. Fix the highlighted rows and upload again."),
      ).toBeInTheDocument();
    });

    const blockingSection = screen.getByLabelText("Blocking errors");
    const warningSection = screen.getByLabelText("Warnings");

    expect(within(blockingSection).getByText("Machine_Type is required.")).toBeInTheDocument();
    expect(within(warningSection).getByText("Vendor lead time should be reviewed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Planning run setup next" })).toBeDisabled();
  });

  it("keeps the upload context when validation details need a retry", async () => {
    let resolveRetryValidation: (() => void) | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.endsWith("/api/v1/uploads")) {
        return createJsonResponse({
          id: "upload-3",
          original_filename: "retry.xlsx",
          stored_filename: "retry.xlsx",
          file_hash: "ghi789",
          file_size_bytes: 1024,
          uploaded_by_user_id: "user-1",
          uploaded_at: "2026-04-30T06:20:00.000000Z",
          status: "VALIDATION_FAILED",
          validation_error_count: 1,
          validation_warning_count: 2,
          artifact: {
            id: "artifact-3",
            upload_batch_id: "upload-3",
            storage_path: "data/uploads/upload-3/retry.xlsx",
            mime_type:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            created_at: "2026-04-30T06:20:00.000000Z",
          },
        });
      }

      if (url.endsWith("/api/v1/uploads/upload-3/validation-issues")) {
        if (fetchMock.mock.calls.filter(([call]) => String(call).endsWith("/api/v1/uploads/upload-3/validation-issues")).length === 1) {
          return createJsonResponse(
            {
              detail: {
                code: "VALIDATION_ISSUES_UNAVAILABLE",
                message: "Validation details are temporarily unavailable.",
              },
            },
            { ok: false, status: 503 },
          );
        }

        return new Promise((resolve) => {
          resolveRetryValidation = () =>
            resolve(
              createJsonResponse({
                upload_batch_id: "upload-3",
                summary: { blocking: 1, warning: 2, total: 3 },
                issues: [
                  {
                    id: "issue-4",
                    upload_batch_id: "upload-3",
                    staging_row_id: "row-4",
                    sheet_name: "Valve_Plan",
                    row_number: 8,
                    severity: "BLOCKING",
                    issue_code: "MISSING_DISPATCH_DATE",
                    message: "Dispatch_Date is required.",
                    field_name: "Dispatch_Date",
                    created_at: "2026-04-30T06:20:00.000000Z",
                  },
                  {
                    id: "issue-5",
                    upload_batch_id: "upload-3",
                    staging_row_id: "row-5",
                    sheet_name: "Component_Status",
                    row_number: 3,
                    severity: "WARNING",
                    issue_code: "TENTATIVE_DATE",
                    message: "Expected ready date is tentative and should be reviewed.",
                    field_name: "Expected_Ready_Date",
                    created_at: "2026-04-30T06:20:01.000000Z",
                  },
                  {
                    id: "issue-6",
                    upload_batch_id: "upload-3",
                    staging_row_id: "row-6",
                    sheet_name: "Vendor_Master",
                    row_number: 2,
                    severity: "WARNING",
                    issue_code: "VENDOR_REVIEW",
                    message: "Vendor lead time should be reviewed.",
                    field_name: "Turnaround_Days",
                    created_at: "2026-04-30T06:20:02.000000Z",
                  },
                ],
              }),
            );
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Upload workbook"), {
      target: {
        files: [
          new File(["workbook"], "retry.xlsx", {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload workbook" }));

    await waitFor(() => {
      expect(screen.getByText("Validation details are temporarily unavailable.")).toBeInTheDocument();
    });

    expect(screen.getByText("Validation details are temporarily unavailable. Retry validation details to continue.")).toBeInTheDocument();
    expect(screen.queryByText("No blocking errors.")).not.toBeInTheDocument();
    expect(screen.queryByText("No warnings.")).not.toBeInTheDocument();
    expect(screen.getAllByText("retry.xlsx")).toHaveLength(2);
    const latestUploadSummary = screen.getByText("Latest upload").parentElement;
    expect(latestUploadSummary).not.toBeNull();
    expect(within(latestUploadSummary as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(within(latestUploadSummary as HTMLElement).getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Planning run setup next" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Retry validation details" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Retrying validation details..." })).toBeDisabled();
    });

    const completeRetry: () => void =
      resolveRetryValidation ??
      (() => {
        throw new Error("Retry validation resolver was not set.");
      });
    completeRetry();

    await waitFor(() => {
      expect(
        screen.getByText("Upload has blocking errors. Fix the highlighted rows and upload again."),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("Dispatch_Date is required.")).toBeInTheDocument();
    expect(screen.getByText("Expected ready date is tentative and should be reviewed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Planning run setup next" })).toBeDisabled();
  });

  it("shows the backend upload error message for a valid xlsx that the API rejects", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.endsWith("/api/v1/uploads")) {
        return createJsonResponse(
          {
            detail: {
              code: "UPLOAD_TOO_LARGE",
              message: "Uploaded file exceeds the 25 MB limit.",
            },
          },
          { ok: false, status: 413 },
        );
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Upload workbook"), {
      target: {
        files: [
          new File(["workbook"], "oversize.xlsx", {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload workbook" }));

    await waitFor(() => {
      expect(screen.getByText("Uploaded file exceeds the 25 MB limit.")).toBeInTheDocument();
    });
  });

  it("creates and calculates a planning run, then opens the home dashboard", async () => {
    let createPayload: Record<string, unknown> | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.endsWith("/api/v1/uploads")) {
        return createJsonResponse({
          id: "upload-10",
          original_filename: "plan.xlsx",
          stored_filename: "plan.xlsx",
          file_hash: "abc10",
          file_size_bytes: 4096,
          uploaded_by_user_id: "user-1",
          uploaded_at: "2026-04-30T06:00:00.000000Z",
          status: "VALIDATED",
          validation_error_count: 0,
          validation_warning_count: 0,
          artifact: {
            id: "artifact-10",
            upload_batch_id: "upload-10",
            storage_path: "data/uploads/upload-10/plan.xlsx",
            mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            created_at: "2026-04-30T06:00:00.000000Z",
          },
        });
      }

      if (url.endsWith("/api/v1/uploads/upload-10/validation-issues")) {
        return createJsonResponse({
          upload_batch_id: "upload-10",
          summary: { blocking: 0, warning: 0, total: 0 },
          issues: [],
        });
      }

      if (url.endsWith("/api/v1/planning-runs")) {
        createPayload = JSON.parse(String(init?.body));
        return createJsonResponse(
          {
            id: "run-10",
            upload_batch_id: "upload-10",
            planning_start_date: "2026-05-02",
            planning_horizon_days: 14,
            status: "CREATED",
            created_by_user_id: "user-1",
            created_at: "2026-04-30T06:01:00.000000Z",
            calculated_at: null,
            error_message: null,
            snapshot_id: "snapshot-10",
            canonical_counts: {
              valves: 12,
              component_statuses: 34,
              routing_operations: 56,
              machines: 6,
              vendors: 4,
            },
          },
          { status: 201 },
        );
      }

      if (url.endsWith("/api/v1/planning-runs/run-10/calculate")) {
        return createJsonResponse({
          id: "run-10",
          upload_batch_id: "upload-10",
          planning_start_date: "2026-05-02",
          planning_horizon_days: 14,
          status: "CALCULATED",
          created_by_user_id: "user-1",
          created_at: "2026-04-30T06:01:00.000000Z",
          calculated_at: "2026-04-30T06:02:00.000000Z",
          error_message: null,
          snapshot_id: "snapshot-10",
          canonical_counts: {
            valves: 12,
            component_statuses: 34,
            routing_operations: 56,
            machines: 6,
            vendors: 4,
          },
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-10",
              upload_batch_id: "upload-10",
              planning_start_date: "2026-05-02",
              planning_horizon_days: 14,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:01:00.000000Z",
              calculated_at: "2026-04-30T06:02:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-10",
              canonical_counts: {
                valves: 12,
                component_statuses: 34,
                routing_operations: 56,
                machines: 6,
                vendors: 4,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.endsWith("/api/v1/planning-runs/run-10/dashboard")) {
        return createJsonResponse({
          planning_run_id: "run-10",
          active_valves: 12,
          active_value_cr: 4.5,
          planned_throughput_value_cr: 3.8,
          throughput_gap_cr: 1.2,
          overloaded_machines: 2,
          underutilized_machines: 1,
          flow_blockers: 5,
          assembly_risk_valves: 3,
          subcontract_recommendations: 4,
          batch_risks: 2,
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Upload workbook"), {
      target: {
        files: [
          new File(["workbook"], "plan.xlsx", {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload workbook" }));

    await waitFor(() => {
      expect(screen.getByText("Upload validated. Ready to create planning run.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Planning run setup next" }));
    fireEvent.change(screen.getByLabelText("Planning start date"), {
      target: { value: "2026-05-02" },
    });
    fireEvent.change(screen.getByLabelText("Planning horizon"), {
      target: { value: "14" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create and run planning" }));

    await waitFor(() => {
      expect(screen.getByText("Home dashboard summary")).toBeInTheDocument();
    });

    expect(createPayload).toEqual({
      upload_batch_id: "upload-10",
      planning_start_date: "2026-05-02",
      planning_horizon_days: 14,
    });
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("4.50 Cr")).toBeInTheDocument();
    expect(screen.getByText("Open flow blockers")).toBeInTheDocument();
  });

  it("blocks unsupported file types before the upload request is made", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Upload workbook"), {
      target: {
        files: [new File(["csv"], "plan.csv", { type: "text/csv" })],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload workbook" }));

    expect(screen.getByText("Only .xlsx workbooks are supported.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows a friendly unavailable state when the backend cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Backend unavailable")).toBeInTheDocument();
    });
  });

  it("loads flow blockers across pages and groups them by blocker type", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-11",
              upload_batch_id: "upload-11",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-11",
              canonical_counts: {
                valves: 2,
                component_statuses: 2,
                routing_operations: 2,
                machines: 2,
                vendors: 1,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-11/flow-blockers?page=1&page_size=100")) {
        return createJsonResponse({
          items: [
            {
              id: "blocker-1",
              planned_operation_id: "op-1",
              valve_id: "V-100",
              customer: "Acme",
              component_line_no: 1,
              component: "Body",
              operation_name: "HBM roughing",
              blocker_type: "MISSING_MACHINE",
              cause: "HBM capacity is not active for this run.",
              recommended_action: "Activate HBM capacity or remap the operation.",
              severity: "CRITICAL",
              created_at: "2026-04-30T06:01:00.000000Z",
            },
          ],
          total: 101,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-11/flow-blockers?page=2&page_size=100")) {
        return createJsonResponse({
          items: [
            {
              id: "blocker-2",
              planned_operation_id: "op-2",
              valve_id: "V-200",
              customer: "Beta",
              component_line_no: 1,
              component: "Bonnet",
              operation_name: "Vendor dispatch",
              blocker_type: "VENDOR_OVERLOADED",
              cause: "Selected vendor has already reached the V1 recommendation limit.",
              recommended_action: "Review vendor capacity before accepting the subcontract plan.",
              severity: "WARNING",
              created_at: "2026-04-30T06:02:00.000000Z",
            },
          ],
          total: 101,
          page: 2,
          page_size: 100,
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Flow Blockers" }));

    await waitFor(() => {
      expect(screen.getByText("Grouped blocker review")).toBeInTheDocument();
    });

    expect(screen.getByText("MISSING_MACHINE")).toBeInTheDocument();
    expect(screen.getByText("HBM capacity is not active for this run.")).toBeInTheDocument();
    expect(screen.getByText("VENDOR_OVERLOADED")).toBeInTheDocument();
    expect(screen.getByText("Review vendor capacity before accepting the subcontract plan.")).toBeInTheDocument();
  });

  it("loads machine load and queue detail for the latest calculated planning run", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-1",
              upload_batch_id: "upload-1",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-1",
              canonical_counts: {
                valves: 2,
                component_statuses: 2,
                routing_operations: 3,
                machines: 2,
                vendors: 0,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-1/machine-load?")) {
        return createJsonResponse({
          items: [
            {
              machine_type: "HBM",
              total_operation_hours: 16,
              capacity_hours_per_day: 8,
              load_days: 2,
              buffer_days: 5,
              overload_flag: false,
              overload_days: 0,
              spare_capacity_days: 3,
              underutilized_flag: true,
              batch_risk_flag: true,
              status: "UNDERUTILIZED",
              queue_approximation_warning:
                "Queue is priority-based and aggregated by machine type. Review before execution.",
            },
            {
              machine_type: "VTL",
              total_operation_hours: 4,
              capacity_hours_per_day: 8,
              load_days: 0.5,
              buffer_days: 3,
              overload_flag: false,
              overload_days: 0,
              spare_capacity_days: 2.5,
              underutilized_flag: true,
              batch_risk_flag: false,
              status: "OK",
              queue_approximation_warning:
                "Queue is priority-based and aggregated by machine type. Review before execution.",
            },
          ],
          total: 2,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-1/machine-load/HBM/queue?")) {
        return createJsonResponse({
          machine_type: "HBM",
          queue_approximation_warning:
            "Queue is priority-based and aggregated by machine type. Review before execution.",
          items: [
            {
              id: "op-1",
              sort_sequence: 1,
              priority_score: 105,
              valve_id: "V-100",
              customer: "Acme",
              component_line_no: 1,
              component: "Body",
              operation_no: 10,
              operation_name: "HBM roughing",
              availability_date: "2026-04-21",
              date_confidence: "CONFIRMED",
              operation_hours: 8,
              internal_wait_days: 0,
              processing_time_days: 1,
              internal_completion_date: "2026-04-22",
              recommendation_status: "OK_INTERNAL",
              extreme_delay_flag: false,
            },
            {
              id: "op-2",
              sort_sequence: 2,
              priority_score: 92,
              valve_id: "V-200",
              customer: "Beta",
              component_line_no: 1,
              component: "Bonnet",
              operation_no: 10,
              operation_name: "HBM finish",
              availability_date: "2026-04-21",
              date_confidence: "CONFIRMED",
              operation_hours: 8,
              internal_wait_days: 1,
              processing_time_days: 1,
              internal_completion_date: "2026-04-23",
              recommendation_status: "HOLD_FOR_PRIORITY_FLOW",
              extreme_delay_flag: false,
            },
          ],
          total: 2,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-1/machine-load/VTL/queue?")) {
        return createJsonResponse({
          machine_type: "VTL",
          queue_approximation_warning:
            "Queue is priority-based and aggregated by machine type. Review before execution.",
          items: [
            {
              id: "op-3",
              sort_sequence: 3,
              priority_score: 88,
              valve_id: "V-100",
              customer: "Acme",
              component_line_no: 1,
              component: "Body",
              operation_no: 20,
              operation_name: "VTL finish",
              availability_date: "2026-04-22",
              date_confidence: "CONFIRMED",
              operation_hours: 4,
              internal_wait_days: 0,
              processing_time_days: 0.5,
              internal_completion_date: "2026-04-22",
              recommendation_status: "OK_INTERNAL",
              extreme_delay_flag: false,
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Machine Load" }));

    await waitFor(() => {
      expect(screen.getByText("Latest calculated run")).toBeInTheDocument();
    });

    expect(screen.getByText("Queue is priority-based and aggregated by machine type. Review before execution.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open HBM queue" })).toBeInTheDocument();
    expect(screen.getByText("HBM roughing")).toBeInTheDocument();
    expect(screen.getByText("HBM finish")).toBeInTheDocument();
    expect(screen.getByText("HOLD_FOR_PRIORITY_FLOW")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open VTL queue" }));

    await waitFor(() => {
      expect(screen.getByText("VTL finish")).toBeInTheDocument();
    });
  });

  it("keeps the newest queue selection when earlier queue requests finish later", async () => {
    let resolveHbmQueue: (() => void) | null = null;
    let resolveVtlQueue: (() => void) | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-2",
              upload_batch_id: "upload-2",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-2",
              canonical_counts: {
                valves: 2,
                component_statuses: 2,
                routing_operations: 3,
                machines: 2,
                vendors: 0,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-2/machine-load?")) {
        return createJsonResponse({
          items: [
            {
              machine_type: "HBM",
              total_operation_hours: 16,
              capacity_hours_per_day: 8,
              load_days: 2,
              buffer_days: 5,
              overload_flag: false,
              overload_days: 0,
              spare_capacity_days: 3,
              underutilized_flag: true,
              batch_risk_flag: true,
              status: "UNDERUTILIZED",
              queue_approximation_warning:
                "Queue is priority-based and aggregated by machine type. Review before execution.",
            },
            {
              machine_type: "VTL",
              total_operation_hours: 4,
              capacity_hours_per_day: 8,
              load_days: 0.5,
              buffer_days: 3,
              overload_flag: false,
              overload_days: 0,
              spare_capacity_days: 2.5,
              underutilized_flag: true,
              batch_risk_flag: false,
              status: "OK",
              queue_approximation_warning:
                "Queue is priority-based and aggregated by machine type. Review before execution.",
            },
          ],
          total: 2,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-2/machine-load/HBM/queue?")) {
        return new Promise((resolve) => {
          resolveHbmQueue = () =>
            resolve(
              createJsonResponse({
                machine_type: "HBM",
                queue_approximation_warning:
                  "Queue is priority-based and aggregated by machine type. Review before execution.",
                items: [
                  {
                    id: "op-hbm-1",
                    sort_sequence: 1,
                    priority_score: 105,
                    valve_id: "V-100",
                    customer: "Acme",
                    component_line_no: 1,
                    component: "Body",
                    operation_no: 10,
                    operation_name: "HBM roughing",
                    availability_date: "2026-04-21",
                    date_confidence: "CONFIRMED",
                    operation_hours: 8,
                    internal_wait_days: 0,
                    processing_time_days: 1,
                    internal_completion_date: "2026-04-22",
                    recommendation_status: "OK_INTERNAL",
                    extreme_delay_flag: false,
                  },
                ],
                total: 1,
                page: 1,
                page_size: 100,
              }),
            );
        });
      }

      if (url.includes("/api/v1/planning-runs/run-2/machine-load/VTL/queue?")) {
        return new Promise((resolve) => {
          resolveVtlQueue = () =>
            resolve(
              createJsonResponse({
                machine_type: "VTL",
                queue_approximation_warning:
                  "Queue is priority-based and aggregated by machine type. Review before execution.",
                items: [
                  {
                    id: "op-vtl-1",
                    sort_sequence: 2,
                    priority_score: 88,
                    valve_id: "V-100",
                    customer: "Acme",
                    component_line_no: 1,
                    component: "Body",
                    operation_no: 20,
                    operation_name: "VTL finish",
                    availability_date: "2026-04-22",
                    date_confidence: "CONFIRMED",
                    operation_hours: 4,
                    internal_wait_days: 0,
                    processing_time_days: 0.5,
                    internal_completion_date: "2026-04-22",
                    recommendation_status: "OK_INTERNAL",
                    extreme_delay_flag: false,
                  },
                ],
                total: 1,
                page: 1,
                page_size: 100,
              }),
            );
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Machine Load" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Open VTL queue" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Open VTL queue" }));

    const finishHbmQueue: () => void =
      resolveHbmQueue ??
      (() => {
        throw new Error("HBM queue resolver was not set.");
      });
    finishHbmQueue();

    await waitFor(() => {
      expect(screen.getByText("Loading queue detail...")).toBeInTheDocument();
    });

    expect(screen.queryByText("HBM roughing")).not.toBeInTheDocument();

    const finishVtlQueue: () => void =
      resolveVtlQueue ??
      (() => {
        throw new Error("VTL queue resolver was not set.");
      });
    finishVtlQueue();

    await waitFor(() => {
      expect(screen.getByText("VTL finish")).toBeInTheDocument();
    });

    expect(screen.queryByText("HBM roughing")).not.toBeInTheDocument();
    expect(screen.getByText("VTL queue detail")).toBeInTheDocument();
  });

  it("shows an empty machine load state when no calculated planning run exists yet", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [],
          total: 0,
          page: 1,
          page_size: 1,
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Machine Load" }));

    await waitFor(() => {
      expect(
        screen.getByText("No calculated planning run yet. Finish planning run setup and calculation first."),
      ).toBeInTheDocument();
    });
  });

  it("loads valve readiness, component status, and assembly risk for the latest calculated planning run", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-4",
              upload_batch_id: "upload-4",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-4",
              canonical_counts: {
                valves: 2,
                component_statuses: 3,
                routing_operations: 3,
                machines: 2,
                vendors: 0,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-4/valve-readiness?")) {
        return createJsonResponse({
          items: [
            {
              valve_id: "V-100",
              customer: "Acme",
              assembly_date: "2026-04-22",
              dispatch_date: "2026-05-01",
              value_cr: 1.25,
              total_components: 2,
              ready_components: 1,
              required_components: 2,
              ready_required_count: 1,
              pending_required_count: 1,
              full_kit_flag: false,
              near_ready_flag: true,
              valve_expected_completion_date: "2026-04-25",
              otd_delay_days: 3,
              otd_risk_flag: true,
              readiness_status: "AT_RISK",
              risk_reason: "Missing component",
              valve_flow_gap_days: null,
              valve_flow_imbalance_flag: false,
            },
            {
              valve_id: "V-200",
              customer: "Beta",
              assembly_date: "2026-04-24",
              dispatch_date: "2026-05-02",
              value_cr: 0.5,
              total_components: 1,
              ready_components: 1,
              required_components: 1,
              ready_required_count: 1,
              pending_required_count: 0,
              full_kit_flag: true,
              near_ready_flag: false,
              valve_expected_completion_date: "2026-04-24",
              otd_delay_days: 0,
              otd_risk_flag: false,
              readiness_status: "READY",
              risk_reason: null,
              valve_flow_gap_days: null,
              valve_flow_imbalance_flag: false,
            },
          ],
          total: 2,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-4/assembly-risk?")) {
        return createJsonResponse({
          items: [
            {
              valve_id: "V-100",
              customer: "Acme",
              assembly_date: "2026-04-22",
              expected_completion_date: "2026-04-25",
              assembly_delay_days: 3,
              reason: "Missing component",
              suggested_action: "Expedite missing components and rebalance the valve before assembly.",
              value_cr: 1.25,
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-4/component-status?valve_id=V-100")) {
        return createJsonResponse({
          valve_id: "V-100",
          items: [
            {
              valve_id: "V-100",
              customer: "Acme",
              component_line_no: 1,
              component: "Body",
              current_location: "Stores",
              fabrication_complete: true,
              critical: true,
              availability_date: "2026-04-21",
              date_confidence: "CONFIRMED",
              next_operation_name: "HBM roughing",
              next_machine_type: "HBM",
              internal_wait_days: 0,
              status: "READY",
              blocker_types: [],
              blocker_summary: null,
            },
              {
                valve_id: "V-100",
                customer: "Acme",
                component_line_no: 2,
                component: "Bonnet",
                current_location: "Fabrication",
                fabrication_complete: false,
                critical: true,
                availability_date: "2026-04-30",
                date_confidence: "EXPECTED",
                next_operation_name: "VTL finish",
                next_machine_type: "VTL",
                internal_wait_days: 0.5,
                status: "BLOCKED",
                blocker_types: ["MISSING_COMPONENT"],
                blocker_summary:
                  "Required component Bonnet availability_date 2026-04-30 is outside planning horizon ending 2026-04-28.",
              },
            ],
            total: 2,
            page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-4/component-status?valve_id=V-200")) {
        return createJsonResponse({
          valve_id: "V-200",
          items: [
            {
              valve_id: "V-200",
              customer: "Beta",
              component_line_no: 1,
              component: "Disc",
              current_location: "Ready",
              fabrication_complete: true,
              critical: true,
              availability_date: "2026-04-21",
              date_confidence: "CONFIRMED",
              next_operation_name: "Inspection",
              next_machine_type: "QA",
              internal_wait_days: 0,
              status: "READY",
              blocker_types: [],
              blocker_summary: null,
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Valves" }));

      await waitFor(() => {
        expect(screen.getByText("Latest calculated run")).toBeInTheDocument();
      });

      expect(screen.getAllByText("Missing component")).toHaveLength(2);
      expect(
        screen.getByText(
          "Required component Bonnet availability_date 2026-04-30 is outside planning horizon ending 2026-04-28.",
        ),
      ).toBeInTheDocument();
      expect(screen.getByText("Expedite missing components and rebalance the valve before assembly.")).toBeInTheDocument();
      expect(screen.getByText("EXPECTED")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open V-200" }));

    await waitFor(() => {
      expect(screen.getByText("Disc")).toBeInTheDocument();
    });
  });

  it("loads recommendations, vendor exposure, and the planner action log for the latest calculated planning run", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-7",
              upload_batch_id: "upload-7",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-7",
              canonical_counts: {
                valves: 2,
                component_statuses: 3,
                routing_operations: 3,
                machines: 2,
                vendors: 2,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-7/subcontract-recommendations?")) {
        return createJsonResponse({
          items: [
            {
              id: "rec-1",
              planned_operation_id: "op-1",
              valve_id: "V-100",
              customer: "Acme",
              component_line_no: 1,
              component: "Body",
              operation_name: "HBM boring",
              machine_type: "HBM",
              recommendation_type: "SUBCONTRACT",
              recommendation_status: "SUBCONTRACT",
              suggested_machine_type: null,
              suggested_vendor_id: "VEN-1",
              suggested_vendor_name: "Vendor One",
              internal_wait_days: 5.5,
              processing_time_days: 1.0,
              internal_completion_days: 7.1,
              vendor_total_days: 4.0,
              vendor_gain_days: 3.1,
              subcontract_batch_candidate_count: 2,
              batch_subcontract_opportunity_flag: false,
              reason_codes: ["PRIMARY_OVERLOADED", "SUBCONTRACT_FEASIBLE"],
              explanation:
                "HBM load is 6.2 days against a 4.0 day buffer. Internal completion is 7.1 days from arrival. Vendor completion is 4.0 days from arrival.",
              status: "PENDING",
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-7/vendor-load")) {
        return createJsonResponse({
          items: [
            {
              vendor_id: "VEN-1",
              vendor_name: "Vendor One",
              primary_process: "HBM",
              vendor_recommended_jobs: 1,
              max_recommended_jobs_per_horizon: 3,
              selected_vendor_overloaded_flag: false,
              status: "OK",
              capacity_rating: "High",
              reliability: "A",
              comments: "Trusted for HBM boring",
              limitation_warning:
                "Vendor timing and external pending load are only partially modeled in V1. Confirm before dispatch.",
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-7/planner-overrides")) {
        return createJsonResponse({
          planning_run_id: "run-7",
          overrides: [
            {
              id: "override-1",
              planning_run_id: "run-7",
              recommendation_id: "rec-older",
              entity_type: "RECOMMENDATION",
              entity_id: "rec-older",
              original_recommendation: "NO_FEASIBLE_OPTION",
              override_decision: "REJECT",
              reason: "Vendor quality concern",
              remarks: null,
              stale_flag: false,
              user_id: "user-1",
              user_display_name: "Planner One",
              created_at: "2026-04-30T06:10:00.000000Z",
            },
          ],
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    await waitFor(() => {
      expect(screen.getByText("Subcontract recommendations")).toBeInTheDocument();
    });

    const recommendationSection = screen.getByLabelText("Recommendation table");
    const vendorSection = screen.getByLabelText("Vendor dashboard");
    const actionLogSection = screen.getByLabelText("Planner action log");

    expect(within(recommendationSection).getByText("HBM boring")).toBeInTheDocument();
    expect(within(recommendationSection).getByText("Vendor One")).toBeInTheDocument();
    expect(within(recommendationSection).getByText("PENDING")).toBeInTheDocument();
    expect(
      within(vendorSection).getByText(
        "Vendor timing and external pending load are only partially modeled in V1. Confirm before dispatch.",
      ),
    ).toBeInTheDocument();
    expect(within(vendorSection).getByText("Vendor One")).toBeInTheDocument();
    expect(within(actionLogSection).getByText("Planner One")).toBeInTheDocument();
    expect(within(actionLogSection).getByText("Vendor quality concern")).toBeInTheDocument();
  });

  it("loads recommendation and vendor pages beyond the first page", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-13",
              upload_batch_id: "upload-13",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-13",
              canonical_counts: {
                valves: 2,
                component_statuses: 2,
                routing_operations: 2,
                machines: 2,
                vendors: 2,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-13/subcontract-recommendations?sort=vendor_gain_days&direction=desc&page=1&page_size=100")) {
        return createJsonResponse({
          items: [
            {
              id: "rec-13-1",
              planned_operation_id: "op-13-1",
              valve_id: "V-131",
              customer: "Acme",
              component_line_no: 1,
              component: "Body",
              operation_name: "HBM boring",
              machine_type: "HBM",
              recommendation_type: "SUBCONTRACT",
              recommendation_status: "SUBCONTRACT",
              suggested_machine_type: null,
              suggested_vendor_id: "VEN-13-1",
              suggested_vendor_name: "Vendor One",
              internal_wait_days: 5.5,
              processing_time_days: 1.6,
              internal_completion_days: 7.1,
              vendor_total_days: 4,
              vendor_gain_days: 3.1,
              subcontract_batch_candidate_count: 2,
              batch_subcontract_opportunity_flag: true,
              reason_codes: ["PRIMARY_OVERLOADED", "VENDOR_FASTER"],
              explanation: "Vendor One is faster than the internal HBM queue.",
              status: "PENDING",
            },
          ],
          total: 101,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-13/subcontract-recommendations?sort=vendor_gain_days&direction=desc&page=2&page_size=100")) {
        return createJsonResponse({
          items: [
            {
              id: "rec-13-2",
              planned_operation_id: "op-13-2",
              valve_id: "V-132",
              customer: "Beta",
              component_line_no: 1,
              component: "Disc",
              operation_name: "VTL finish",
              machine_type: "VTL",
              recommendation_type: "NO_FEASIBLE_OPTION",
              recommendation_status: "NO_FEASIBLE_OPTION",
              suggested_machine_type: null,
              suggested_vendor_id: null,
              suggested_vendor_name: null,
              internal_wait_days: 4.2,
              processing_time_days: 1.0,
              internal_completion_days: 5.2,
              vendor_total_days: null,
              vendor_gain_days: null,
              subcontract_batch_candidate_count: null,
              batch_subcontract_opportunity_flag: false,
              reason_codes: ["PRIMARY_OVERLOADED", "NO_APPROVED_VENDOR"],
              explanation: "No approved vendor exists for the second operation.",
              status: "PENDING",
            },
          ],
          total: 101,
          page: 2,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-13/vendor-load?page=1&page_size=100")) {
        return createJsonResponse({
          items: [
            {
              vendor_id: "VEN-13-1",
              vendor_name: "Vendor One",
              primary_process: "HBM",
              vendor_recommended_jobs: 1,
              max_recommended_jobs_per_horizon: 3,
              selected_vendor_overloaded_flag: false,
              status: "OK",
              capacity_rating: "High",
              reliability: "A",
              comments: "Trusted",
              limitation_warning:
                "Vendor timing and external pending load are only partially modeled in V1. Confirm before dispatch.",
            },
          ],
          total: 101,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-13/vendor-load?page=2&page_size=100")) {
        return createJsonResponse({
          items: [
            {
              vendor_id: "VEN-13-2",
              vendor_name: "Vendor Two",
              primary_process: "VTL",
              vendor_recommended_jobs: 1,
              max_recommended_jobs_per_horizon: 2,
              selected_vendor_overloaded_flag: false,
              status: "OK",
              capacity_rating: "Medium",
              reliability: "B",
              comments: "Secondary option",
              limitation_warning:
                "Vendor timing and external pending load are only partially modeled in V1. Confirm before dispatch.",
            },
          ],
          total: 101,
          page: 2,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-13/planner-overrides")) {
        return createJsonResponse({
          planning_run_id: "run-13",
          overrides: [],
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    await waitFor(() => {
      expect(screen.getByText("No approved vendor exists for the second operation.")).toBeInTheDocument();
    });

    const recommendationSection = screen.getByLabelText("Recommendation table");
    const vendorSection = screen.getByLabelText("Vendor dashboard");

    expect(within(recommendationSection).getByText("Body")).toBeInTheDocument();
    expect(within(recommendationSection).getByText("Disc")).toBeInTheDocument();
    expect(within(vendorSection).getByText("Vendor One")).toBeInTheDocument();
    expect(within(vendorSection).getByText("Vendor Two")).toBeInTheDocument();
  });

  it("requires a reason for planner decisions and updates recommendation status plus action log after save", async () => {
    let postCount = 0;
    const overrides: Array<{
      id: string;
      planning_run_id: string;
      recommendation_id: string | null;
      entity_type: string;
      entity_id: string;
      original_recommendation: string | null;
      override_decision: string;
      reason: string;
      remarks: string | null;
      stale_flag: boolean;
      user_id: string;
      user_display_name: string;
      created_at: string;
    }> = [];

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-8",
              upload_batch_id: "upload-8",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-8",
              canonical_counts: {
                valves: 1,
                component_statuses: 1,
                routing_operations: 1,
                machines: 1,
                vendors: 1,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-8/subcontract-recommendations?")) {
        return createJsonResponse({
          items: [
            {
              id: "rec-2",
              planned_operation_id: "op-2",
              valve_id: "V-200",
              customer: "Beta",
              component_line_no: 1,
              component: "Bonnet",
              operation_name: "VTL finish",
              machine_type: "VTL",
              recommendation_type: "NO_FEASIBLE_OPTION",
              recommendation_status: "NO_FEASIBLE_OPTION",
              suggested_machine_type: null,
              suggested_vendor_id: null,
              suggested_vendor_name: null,
              internal_wait_days: 4.2,
              processing_time_days: 1.0,
              internal_completion_days: 5.2,
              vendor_total_days: null,
              vendor_gain_days: null,
              subcontract_batch_candidate_count: null,
              batch_subcontract_opportunity_flag: false,
              reason_codes: ["PRIMARY_OVERLOADED", "NO_APPROVED_VENDOR"],
              explanation: "No approved vendor exists and VTL remains overloaded.",
              status: "PENDING",
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-8/vendor-load")) {
        return createJsonResponse({
          items: [],
          total: 0,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-8/planner-overrides")) {
        return createJsonResponse({
          planning_run_id: "run-8",
          overrides,
        });
      }

      if (url.endsWith("/api/v1/planner-overrides")) {
        postCount += 1;
        const payload = JSON.parse(String(init?.body)) as {
          planning_run_id: string;
          entity_type: string;
          entity_id: string;
          override_decision: string;
          reason: string;
          remarks?: string | null;
          original_recommendation?: string | null;
        };

        const override = {
          id: "override-new",
          planning_run_id: payload.planning_run_id,
          recommendation_id: payload.entity_id,
          entity_type: payload.entity_type,
          entity_id: payload.entity_id,
          original_recommendation: payload.original_recommendation ?? null,
          override_decision: payload.override_decision,
          reason: payload.reason,
          remarks: payload.remarks ?? null,
          stale_flag: false,
          user_id: "user-1",
          user_display_name: "Planner One",
          created_at: "2026-04-30T06:20:00.000000Z",
        };
        overrides.unshift(override);
        return createJsonResponse(override, { status: 201 });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    await waitFor(() => {
      expect(screen.getByText("No approved vendor exists and VTL remains overloaded.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));

    expect(screen.getByText("Reason is required before saving a planner decision.")).toBeInTheDocument();
    expect(postCount).toBe(0);

    fireEvent.change(screen.getByLabelText("Decision reason"), {
      target: { value: "Customer escalation" },
    });
    fireEvent.change(screen.getByLabelText("Remarks"), {
      target: { value: "Approve vendor path for this urgent order." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() => {
      expect(screen.getByText("Decision recorded.")).toBeInTheDocument();
    });

    const recommendationSection = screen.getByLabelText("Recommendation table");
    const actionLogSection = screen.getByLabelText("Planner action log");

    expect(postCount).toBe(1);
    expect(within(recommendationSection).getByText("ACCEPTED")).toBeInTheDocument();
    expect(within(actionLogSection).getByText("Planner One")).toBeInTheDocument();
    expect(within(actionLogSection).getByText("Customer escalation")).toBeInTheDocument();
    expect(within(actionLogSection).getByText("Accept")).toBeInTheDocument();
  });

  it("records override decisions and marks the recommendation as overridden", async () => {
    const overrides: Array<{
      id: string;
      planning_run_id: string;
      recommendation_id: string | null;
      entity_type: string;
      entity_id: string;
      original_recommendation: string | null;
      override_decision: string;
      reason: string;
      remarks: string | null;
      stale_flag: boolean;
      user_id: string;
      user_display_name: string;
      created_at: string;
    }> = [];

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-9",
              upload_batch_id: "upload-9",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-9",
              canonical_counts: {
                valves: 1,
                component_statuses: 1,
                routing_operations: 1,
                machines: 2,
                vendors: 1,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-9/subcontract-recommendations?")) {
        return createJsonResponse({
          items: [
            {
              id: "rec-9",
              planned_operation_id: "op-9",
              valve_id: "V-900",
              customer: "Gamma",
              component_line_no: 1,
              component: "Seat",
              operation_name: "HBM finish",
              machine_type: "HBM",
              recommendation_type: "USE_ALTERNATE",
              recommendation_status: "USE_ALTERNATE",
              suggested_machine_type: "VTL",
              suggested_vendor_id: null,
              suggested_vendor_name: null,
              internal_wait_days: 3.5,
              processing_time_days: 1.1,
              internal_completion_days: 4.6,
              vendor_total_days: null,
              vendor_gain_days: null,
              subcontract_batch_candidate_count: null,
              batch_subcontract_opportunity_flag: false,
              reason_codes: ["PRIMARY_OVERLOADED", "ALTERNATE_CAPACITY_AVAILABLE"],
              explanation: "HBM is overloaded and VTL stays within buffer after reassignment.",
              status: "PENDING",
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-9/vendor-load")) {
        return createJsonResponse({
          items: [],
          total: 0,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-9/planner-overrides")) {
        return createJsonResponse({
          planning_run_id: "run-9",
          overrides,
        });
      }

      if (url.endsWith("/api/v1/planner-overrides")) {
        const payload = JSON.parse(String(init?.body)) as {
          planning_run_id: string;
          entity_type: string;
          entity_id: string;
          override_decision: string;
          reason: string;
          remarks?: string | null;
          original_recommendation?: string | null;
        };

        const override = {
          id: "override-9",
          planning_run_id: payload.planning_run_id,
          recommendation_id: payload.entity_id,
          entity_type: payload.entity_type,
          entity_id: payload.entity_id,
          original_recommendation: payload.original_recommendation ?? null,
          override_decision: payload.override_decision,
          reason: payload.reason,
          remarks: payload.remarks ?? null,
          stale_flag: false,
          user_id: "user-1",
          user_display_name: "Planner One",
          created_at: "2026-04-30T06:30:00.000000Z",
        };
        overrides.unshift(override);
        return createJsonResponse(override, { status: 201 });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    await waitFor(() => {
      expect(screen.getByText("HBM is overloaded and VTL stays within buffer after reassignment.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Override" }));
    fireEvent.change(screen.getByLabelText("Override choice"), {
      target: { value: "FORCE_VENDOR" },
    });
    fireEvent.change(screen.getByLabelText("Decision reason"), {
      target: { value: "Bundle with existing vendor shipment" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() => {
      expect(screen.getByText("Decision recorded.")).toBeInTheDocument();
    });

    const recommendationSection = screen.getByLabelText("Recommendation table");
    const actionLogSection = screen.getByLabelText("Planner action log");

    expect(within(recommendationSection).getByText("OVERRIDDEN")).toBeInTheDocument();
    expect(within(actionLogSection).getByText("Force Vendor")).toBeInTheDocument();
    expect(within(actionLogSection).getByText("Bundle with existing vendor shipment")).toBeInTheDocument();
  });

  it("keeps valve readiness visible when assembly risk fails to load", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-5",
              upload_batch_id: "upload-5",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-5",
              canonical_counts: {
                valves: 1,
                component_statuses: 1,
                routing_operations: 1,
                machines: 1,
                vendors: 0,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-5/valve-readiness?")) {
        return createJsonResponse({
          items: [
            {
              valve_id: "V-100",
              customer: "Acme",
              assembly_date: "2026-04-22",
              dispatch_date: "2026-05-01",
              value_cr: 1.25,
              total_components: 1,
              ready_components: 1,
              required_components: 1,
              ready_required_count: 1,
              pending_required_count: 0,
              full_kit_flag: true,
              near_ready_flag: false,
              valve_expected_completion_date: "2026-04-22",
              otd_delay_days: 0,
              otd_risk_flag: false,
              readiness_status: "READY",
              risk_reason: null,
              valve_flow_gap_days: null,
              valve_flow_imbalance_flag: false,
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-5/assembly-risk?")) {
        return createJsonResponse(
          {
            detail: {
              code: "ASSEMBLY_RISK_UNAVAILABLE",
              message: "Assembly risk temporarily unavailable.",
            },
          },
          { ok: false, status: 503 },
        );
      }

      if (url.includes("/api/v1/planning-runs/run-5/component-status?valve_id=V-100")) {
        return createJsonResponse({
          valve_id: "V-100",
          items: [
            {
              valve_id: "V-100",
              customer: "Acme",
              component_line_no: 1,
              component: "Body",
              current_location: "Stores",
              fabrication_complete: true,
              critical: true,
              availability_date: "2026-04-21",
              date_confidence: "CONFIRMED",
              next_operation_name: "HBM roughing",
              next_machine_type: "HBM",
              internal_wait_days: 0,
              status: "READY",
              blocker_types: [],
              blocker_summary: null,
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Valves" }));

    await waitFor(() => {
      expect(screen.getByText("Valve readiness")).toBeInTheDocument();
    });

    expect(screen.getByText("Assembly risk temporarily unavailable.")).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
    expect(screen.queryByText("Valve readiness and assembly risk could not be loaded. Retry when the API is ready.")).not.toBeInTheDocument();
  });

  it("keeps the newest valve selection when earlier component detail requests finish later", async () => {
    let resolveV100ComponentStatus: (() => void) | null = null;
    let resolveV200ComponentStatus: (() => void) | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-6",
              upload_batch_id: "upload-6",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-6",
              canonical_counts: {
                valves: 2,
                component_statuses: 2,
                routing_operations: 2,
                machines: 1,
                vendors: 0,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-6/valve-readiness?")) {
        return createJsonResponse({
          items: [
            {
              valve_id: "V-100",
              customer: "Acme",
              assembly_date: "2026-04-22",
              dispatch_date: "2026-05-01",
              value_cr: 1.25,
              total_components: 1,
              ready_components: 1,
              required_components: 1,
              ready_required_count: 1,
              pending_required_count: 0,
              full_kit_flag: true,
              near_ready_flag: false,
              valve_expected_completion_date: "2026-04-22",
              otd_delay_days: 0,
              otd_risk_flag: false,
              readiness_status: "READY",
              risk_reason: null,
              valve_flow_gap_days: null,
              valve_flow_imbalance_flag: false,
            },
            {
              valve_id: "V-200",
              customer: "Beta",
              assembly_date: "2026-04-24",
              dispatch_date: "2026-05-02",
              value_cr: 0.5,
              total_components: 1,
              ready_components: 1,
              required_components: 1,
              ready_required_count: 1,
              pending_required_count: 0,
              full_kit_flag: true,
              near_ready_flag: false,
              valve_expected_completion_date: "2026-04-24",
              otd_delay_days: 0,
              otd_risk_flag: false,
              readiness_status: "READY",
              risk_reason: null,
              valve_flow_gap_days: null,
              valve_flow_imbalance_flag: false,
            },
          ],
          total: 2,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-6/assembly-risk?")) {
        return createJsonResponse({
          items: [],
          total: 0,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-6/component-status?valve_id=V-100")) {
        return new Promise((resolve) => {
          resolveV100ComponentStatus = () =>
            resolve(
              createJsonResponse({
                valve_id: "V-100",
                items: [
                  {
                    valve_id: "V-100",
                    customer: "Acme",
                    component_line_no: 1,
                    component: "Body",
                    current_location: "Stores",
                    fabrication_complete: true,
                    critical: true,
                    availability_date: "2026-04-21",
                    date_confidence: "CONFIRMED",
                    next_operation_name: "HBM roughing",
                    next_machine_type: "HBM",
                    internal_wait_days: 0,
                    status: "READY",
                    blocker_types: [],
                    blocker_summary: null,
                  },
                ],
                total: 1,
                page: 1,
                page_size: 100,
              }),
            );
        });
      }

      if (url.includes("/api/v1/planning-runs/run-6/component-status?valve_id=V-200")) {
        return new Promise((resolve) => {
          resolveV200ComponentStatus = () =>
            resolve(
              createJsonResponse({
                valve_id: "V-200",
                items: [
                  {
                    valve_id: "V-200",
                    customer: "Beta",
                    component_line_no: 1,
                    component: "Disc",
                    current_location: "Ready",
                    fabrication_complete: true,
                    critical: true,
                    availability_date: "2026-04-21",
                    date_confidence: "CONFIRMED",
                    next_operation_name: "Inspection",
                    next_machine_type: "QA",
                    internal_wait_days: 0,
                    status: "READY",
                    blocker_types: [],
                    blocker_summary: null,
                  },
                ],
                total: 1,
                page: 1,
                page_size: 100,
              }),
            );
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Valves" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Open V-200" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Open V-200" }));

    const finishV100: () => void =
      resolveV100ComponentStatus ??
      (() => {
        throw new Error("V-100 component status resolver was not set.");
      });
    finishV100();

    await waitFor(() => {
      expect(screen.getByText("Loading component status...")).toBeInTheDocument();
    });

    expect(screen.queryByText("Body")).not.toBeInTheDocument();

    const finishV200: () => void =
      resolveV200ComponentStatus ??
      (() => {
        throw new Error("V-200 component status resolver was not set.");
      });
    finishV200();

    await waitFor(() => {
      expect(screen.getByText("Disc")).toBeInTheDocument();
    });

    expect(screen.queryByText("Body")).not.toBeInTheDocument();
    expect(screen.getByText("V-200 component status")).toBeInTheDocument();
  });

  it("reloads machine load automatically when the user leaves and returns to the tab", async () => {
    let latestRunRequests = 0;

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        latestRunRequests += 1;

        if (latestRunRequests === 1) {
          return createJsonResponse({
            items: [],
            total: 0,
            page: 1,
            page_size: 1,
          });
        }

        return createJsonResponse({
          items: [
            {
              id: "run-3",
              upload_batch_id: "upload-3",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-3",
              canonical_counts: {
                valves: 1,
                component_statuses: 1,
                routing_operations: 1,
                machines: 1,
                vendors: 0,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-3/machine-load?")) {
        return createJsonResponse({
          items: [
            {
              machine_type: "HBM",
              total_operation_hours: 8,
              capacity_hours_per_day: 8,
              load_days: 1,
              buffer_days: 5,
              overload_flag: false,
              overload_days: 0,
              spare_capacity_days: 4,
              underutilized_flag: true,
              batch_risk_flag: false,
              status: "UNDERUTILIZED",
              queue_approximation_warning:
                "Queue is priority-based and aggregated by machine type. Review before execution.",
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      if (url.includes("/api/v1/planning-runs/run-3/machine-load/HBM/queue?")) {
        return createJsonResponse({
          machine_type: "HBM",
          queue_approximation_warning:
            "Queue is priority-based and aggregated by machine type. Review before execution.",
          items: [
            {
              id: "op-4",
              sort_sequence: 1,
              priority_score: 96,
              valve_id: "V-300",
              customer: "Gamma",
              component_line_no: 1,
              component: "Body",
              operation_no: 10,
              operation_name: "HBM roughing",
              availability_date: "2026-04-22",
              date_confidence: "CONFIRMED",
              operation_hours: 8,
              internal_wait_days: 0,
              processing_time_days: 1,
              internal_completion_date: "2026-04-23",
              recommendation_status: "OK_INTERNAL",
              extreme_delay_flag: false,
            },
          ],
          total: 1,
          page: 1,
          page_size: 100,
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Machine Load" }));

    await waitFor(() => {
      expect(
        screen.getByText("No calculated planning run yet. Finish planning run setup and calculation first."),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    fireEvent.click(screen.getByRole("button", { name: "Machine Load" }));

    await waitFor(() => {
      expect(screen.getByText("Latest calculated run")).toBeInTheDocument();
    });

    expect(screen.getByText("HBM roughing")).toBeInTheDocument();
  });

  it("loads the reports workspace and generates a downloadable workbook", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/api/v1/health")) {
        return createJsonResponse({
          status: "ok",
          app_name: "Machine Shop Planning Software",
          version: "0.1.0",
          environment: "local",
        });
      }

      if (url.includes("/api/v1/planning-runs?latest_only=true")) {
        return createJsonResponse({
          items: [
            {
              id: "run-20",
              upload_batch_id: "upload-20",
              planning_start_date: "2026-04-21",
              planning_horizon_days: 7,
              status: "CALCULATED",
              created_by_user_id: "user-1",
              created_at: "2026-04-30T06:00:00.000000Z",
              calculated_at: "2026-04-30T06:05:00.000000Z",
              error_message: null,
              snapshot_id: "snapshot-20",
              canonical_counts: {
                valves: 2,
                component_statuses: 2,
                routing_operations: 3,
                machines: 2,
                vendors: 2,
              },
            },
          ],
          total: 1,
          page: 1,
          page_size: 1,
        });
      }

      if (url.endsWith("/api/v1/planning-runs/run-20/exports")) {
        expect(init?.method).toBe("POST");
        return createJsonResponse({
          id: "export-20",
          planning_run_id: "run-20",
          report_type: "MACHINE_LOAD",
          file_path: "data/exports/run-20/machine_load.xlsx",
          file_format: "XLSX",
          generated_by_user_id: "user-1",
          generated_at: "2026-05-01T09:00:00.000000Z",
          metadata: {
            sheet_names: ["Machine_Load"],
            sheet_row_counts: { Machine_Load: 2 },
          },
          download_url: "/api/v1/exports/export-20/download",
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Reports" }));

    await waitFor(() => {
      expect(screen.getByText("First usable build exports")).toBeInTheDocument();
    });

    const machineLoadCard = screen.getByText("Machine Load Report").closest("section");
    expect(machineLoadCard).not.toBeNull();

    fireEvent.click(within(machineLoadCard as HTMLElement).getByRole("button", { name: "Generate workbook" }));

    await waitFor(() => {
      expect(screen.getByText("Machine Load Report generated.")).toBeInTheDocument();
    });

    const downloadLink = within(machineLoadCard as HTMLElement).getByRole("link", { name: "Download" });
    expect(downloadLink).toHaveAttribute(
      "href",
      "http://127.0.0.1:8000/api/v1/exports/export-20/download",
    );
  });
});
