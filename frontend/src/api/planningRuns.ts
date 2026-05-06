import { ApiError } from "./uploads";

const defaultApiBaseUrl = "http://127.0.0.1:8000";

export interface CanonicalCountsResponse {
  valves: number;
  component_statuses: number;
  routing_operations: number;
  machines: number;
  vendors: number;
}

export interface PlanningRunResponse {
  id: string;
  upload_batch_id: string;
  planning_start_date: string;
  planning_horizon_days: number;
  status: string;
  created_by_user_id: string;
  created_at: string;
  calculated_at: string | null;
  error_message: string | null;
  snapshot_id: string;
  canonical_counts: CanonicalCountsResponse;
}

interface PlanningRunListResponse {
  items: PlanningRunResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface PlanningRunDashboardSummaryResponse {
  planning_run_id: string;
  active_valves: number;
  active_value_cr: number;
  planned_throughput_value_cr: number;
  throughput_gap_cr: number;
  overloaded_machines: number;
  underutilized_machines: number;
  flow_blockers: number;
  assembly_risk_valves: number;
  subcontract_recommendations: number;
  batch_risks: number;
}

export interface MachineLoadSummaryResponse {
  machine_type: string;
  total_operation_hours: number;
  capacity_hours_per_day: number;
  load_days: number;
  buffer_days: number;
  overload_flag: boolean;
  overload_days: number;
  spare_capacity_days: number;
  underutilized_flag: boolean;
  batch_risk_flag: boolean;
  status: string;
  queue_approximation_warning: string;
}

interface MachineLoadListResponse {
  items: MachineLoadSummaryResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface QueueOperationResponse {
  id: string;
  sort_sequence: number;
  priority_score: number;
  valve_id: string;
  customer: string;
  component_line_no: number;
  component: string;
  operation_no: number;
  operation_name: string;
  availability_date: string;
  date_confidence: string;
  operation_hours: number;
  internal_wait_days: number | null;
  processing_time_days: number | null;
  internal_completion_date: string | null;
  recommendation_status: string | null;
  extreme_delay_flag: boolean | null;
}

export interface QueueOperationListResponse {
  machine_type: string;
  queue_approximation_warning: string | null;
  items: QueueOperationResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ValveReadinessItemResponse {
  valve_id: string;
  customer: string;
  assembly_date: string;
  dispatch_date: string;
  value_cr: number;
  total_components: number;
  ready_components: number;
  required_components: number;
  ready_required_count: number;
  pending_required_count: number;
  full_kit_flag: boolean;
  near_ready_flag: boolean;
  valve_expected_completion_date: string | null;
  otd_delay_days: number;
  otd_risk_flag: boolean;
  readiness_status: string;
  risk_reason: string | null;
  valve_flow_gap_days: number | null;
  valve_flow_imbalance_flag: boolean;
}

interface ValveReadinessListResponse {
  items: ValveReadinessItemResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ComponentStatusItemResponse {
  valve_id: string;
  customer: string;
  component_line_no: number;
  component: string;
  current_location: string | null;
  fabrication_complete: boolean;
  critical: boolean;
  availability_date: string;
  date_confidence: string;
  next_operation_name: string | null;
  next_machine_type: string | null;
  internal_wait_days: number | null;
  status: string;
  blocker_types: string[];
  blocker_summary: string | null;
}

export interface ComponentStatusListResponse {
  valve_id: string;
  items: ComponentStatusItemResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface AssemblyRiskItemResponse {
  valve_id: string;
  customer: string;
  assembly_date: string;
  expected_completion_date: string | null;
  assembly_delay_days: number;
  reason: string | null;
  suggested_action: string;
  value_cr: number;
}

interface AssemblyRiskListResponse {
  items: AssemblyRiskItemResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface RecommendationItemResponse {
  id: string;
  planned_operation_id: string | null;
  valve_id: string | null;
  customer: string | null;
  component_line_no: number | null;
  component: string | null;
  operation_name: string | null;
  machine_type: string | null;
  recommendation_type: string;
  recommendation_status: string | null;
  suggested_machine_type: string | null;
  suggested_vendor_id: string | null;
  suggested_vendor_name: string | null;
  internal_wait_days: number | null;
  processing_time_days: number | null;
  internal_completion_days: number | null;
  vendor_total_days: number | null;
  vendor_gain_days: number | null;
  subcontract_batch_candidate_count: number | null;
  batch_subcontract_opportunity_flag: boolean;
  reason_codes: string[];
  explanation: string;
  status: string;
}

interface RecommendationListResponse {
  items: RecommendationItemResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface FlowBlockerItemResponse {
  id: string;
  planned_operation_id: string | null;
  valve_id: string | null;
  customer: string | null;
  component_line_no: number | null;
  component: string | null;
  operation_name: string | null;
  blocker_type: string;
  cause: string;
  recommended_action: string;
  severity: string;
  created_at: string;
}

interface FlowBlockerListResponse {
  items: FlowBlockerItemResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface VendorLoadItemResponse {
  vendor_id: string;
  vendor_name: string;
  primary_process: string;
  vendor_recommended_jobs: number;
  max_recommended_jobs_per_horizon: number;
  selected_vendor_overloaded_flag: boolean;
  status: string;
  capacity_rating: string | null;
  reliability: string | null;
  comments: string | null;
  limitation_warning: string;
}

interface VendorLoadListResponse {
  items: VendorLoadItemResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface PlannerOverrideResponse {
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
}

interface PlannerOverrideListResponse {
  planning_run_id: string;
  overrides: PlannerOverrideResponse[];
}

export type ReportType =
  | "MACHINE_LOAD"
  | "SUBCONTRACT_PLAN"
  | "VALVE_READINESS"
  | "FLOW_BLOCKER"
  | "DAILY_EXECUTION";

export interface ReportExportResponse {
  id: string;
  planning_run_id: string;
  report_type: string;
  file_path: string;
  file_format: string;
  generated_by_user_id: string;
  generated_at: string;
  metadata: {
    sheet_names: string[];
    sheet_row_counts: Record<string, number>;
  } | null;
  download_url: string;
}

function apiBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl).replace(/\/$/, "");
}

async function parseError(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: { code?: string; message?: string } };
    const detail = payload.detail;
    if (detail?.message) {
      throw new ApiError(detail.message, detail.code ?? null);
    }
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
  }

  throw new ApiError(`Request failed with status ${response.status}.`);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`);

  if (!response.ok) {
    await parseError(response);
  }

  return (await response.json()) as T;
}

function withAbsoluteApiUrl(path: string) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }

  return `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

async function getAllPages<TItem, TResponse extends { items: TItem[]; total: number; page: number; page_size: number }>(
  pathFactory: (page: number) => string,
): Promise<TResponse> {
  const firstPage = await getJson<TResponse>(pathFactory(1));
  const items = [...firstPage.items];
  const totalPages = Math.ceil(firstPage.total / firstPage.page_size);

  for (let page = 2; page <= totalPages; page += 1) {
    const nextPage = await getJson<TResponse>(pathFactory(page));
    items.push(...nextPage.items);
  }

  return {
    ...firstPage,
    items,
  };
}

export async function createPlanningRun(request: {
  upload_batch_id: string;
  planning_start_date: string;
  planning_horizon_days: 7 | 14;
}): Promise<PlanningRunResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/planning-runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    await parseError(response);
  }

  return (await response.json()) as PlanningRunResponse;
}

export async function createPlanningRunExport(
  planningRunId: string,
  request: { report_type: ReportType; file_format: "XLSX" },
): Promise<ReportExportResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/planning-runs/${planningRunId}/exports`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    await parseError(response);
  }

  const payload = (await response.json()) as ReportExportResponse;
  return {
    ...payload,
    download_url: withAbsoluteApiUrl(payload.download_url),
  };
}

export async function calculatePlanningRun(planningRunId: string): Promise<PlanningRunResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/planning-runs/${planningRunId}/calculate`, {
    method: "POST",
  });

  if (!response.ok) {
    await parseError(response);
  }

  return (await response.json()) as PlanningRunResponse;
}

export async function fetchLatestCalculatedPlanningRun(): Promise<PlanningRunResponse | null> {
  const payload = await getJson<PlanningRunListResponse>("/api/v1/planning-runs?latest_only=true");
  return payload.items[0] ?? null;
}

export async function fetchPlanningRunDashboardSummary(
  planningRunId: string,
): Promise<PlanningRunDashboardSummaryResponse> {
  return getJson<PlanningRunDashboardSummaryResponse>(`/api/v1/planning-runs/${planningRunId}/dashboard`);
}

export async function fetchMachineLoad(planningRunId: string): Promise<MachineLoadListResponse> {
  return getJson<MachineLoadListResponse>(
    `/api/v1/planning-runs/${planningRunId}/machine-load?sort=load_days&direction=desc&page=1&page_size=100`,
  );
}

export async function fetchMachineQueue(
  planningRunId: string,
  machineType: string,
): Promise<QueueOperationListResponse> {
  return getJson<QueueOperationListResponse>(
    `/api/v1/planning-runs/${planningRunId}/machine-load/${encodeURIComponent(machineType)}/queue?sort=sort_sequence&direction=asc&page=1&page_size=100`,
  );
}

export async function fetchValveReadiness(planningRunId: string): Promise<ValveReadinessListResponse> {
  return getJson<ValveReadinessListResponse>(
    `/api/v1/planning-runs/${planningRunId}/valve-readiness?sort=assembly_date&direction=asc&page=1&page_size=100`,
  );
}

export async function fetchComponentStatus(
  planningRunId: string,
  valveId: string,
): Promise<ComponentStatusListResponse> {
  return getJson<ComponentStatusListResponse>(
    `/api/v1/planning-runs/${planningRunId}/component-status?valve_id=${encodeURIComponent(valveId)}&page=1&page_size=100`,
  );
}

export async function fetchAssemblyRisk(planningRunId: string): Promise<AssemblyRiskListResponse> {
  return getJson<AssemblyRiskListResponse>(`/api/v1/planning-runs/${planningRunId}/assembly-risk?page=1&page_size=100`);
}

export async function fetchRecommendations(planningRunId: string): Promise<RecommendationListResponse> {
  return getAllPages<RecommendationItemResponse, RecommendationListResponse>(
    (page) =>
      `/api/v1/planning-runs/${planningRunId}/subcontract-recommendations?sort=vendor_gain_days&direction=desc&page=${page}&page_size=100`,
  );
}

export async function fetchVendorLoad(planningRunId: string): Promise<VendorLoadListResponse> {
  return getAllPages<VendorLoadItemResponse, VendorLoadListResponse>(
    (page) => `/api/v1/planning-runs/${planningRunId}/vendor-load?page=${page}&page_size=100`,
  );
}

export async function fetchPlannerOverrides(planningRunId: string): Promise<PlannerOverrideListResponse> {
  return getJson<PlannerOverrideListResponse>(`/api/v1/planning-runs/${planningRunId}/planner-overrides`);
}

export async function fetchFlowBlockers(planningRunId: string): Promise<FlowBlockerListResponse> {
  return getAllPages<FlowBlockerItemResponse, FlowBlockerListResponse>(
    (page) => `/api/v1/planning-runs/${planningRunId}/flow-blockers?page=${page}&page_size=100`,
  );
}

export async function createPlannerOverride(request: {
  planning_run_id: string;
  entity_type: "RECOMMENDATION";
  entity_id: string;
  original_recommendation?: string | null;
  override_decision: string;
  reason: string;
  remarks?: string | null;
}): Promise<PlannerOverrideResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/planner-overrides`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    await parseError(response);
  }

  return (await response.json()) as PlannerOverrideResponse;
}
