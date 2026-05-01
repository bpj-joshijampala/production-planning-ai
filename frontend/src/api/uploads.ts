const defaultApiBaseUrl = "http://127.0.0.1:8000";

export interface RawUploadArtifactResponse {
  id: string;
  upload_batch_id: string;
  storage_path: string;
  mime_type: string | null;
  created_at: string;
}

export interface UploadBatchResponse {
  id: string;
  original_filename: string;
  stored_filename: string;
  file_hash: string;
  file_size_bytes: number;
  uploaded_by_user_id: string;
  uploaded_at: string;
  status: string;
  validation_error_count: number;
  validation_warning_count: number;
  artifact: RawUploadArtifactResponse;
}

export interface ValidationIssueResponse {
  id: string;
  upload_batch_id: string;
  staging_row_id: string | null;
  sheet_name: string | null;
  row_number: number | null;
  severity: "BLOCKING" | "WARNING" | string;
  issue_code: string;
  message: string;
  field_name: string | null;
  created_at: string;
}

export interface ValidationIssuesResponse {
  upload_batch_id: string;
  summary: {
    blocking: number;
    warning: number;
    total: number;
  };
  issues: ValidationIssueResponse[];
}

export class ApiError extends Error {
  code: string | null;

  constructor(message: string, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
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

export async function uploadWorkbook(file: File): Promise<UploadBatchResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${apiBaseUrl()}/api/v1/uploads`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    await parseError(response);
  }

  return (await response.json()) as UploadBatchResponse;
}

export async function fetchValidationIssues(uploadBatchId: string): Promise<ValidationIssuesResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/uploads/${uploadBatchId}/validation-issues`);

  if (!response.ok) {
    await parseError(response);
  }

  return (await response.json()) as ValidationIssuesResponse;
}
