export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  environment: string;
}

const defaultApiBaseUrl = "http://127.0.0.1:8000";

export async function fetchHealth(apiBaseUrl = import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl) {
  const baseUrl = apiBaseUrl.replace(/\/$/, "");
  const response = await fetch(`${baseUrl}/api/v1/health`);

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return (await response.json()) as HealthResponse;
}
