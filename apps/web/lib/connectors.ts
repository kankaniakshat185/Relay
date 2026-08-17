import { API_URL, apiFetch } from "./api";

export type ConnectorProvider = "github" | "slack" | "jira";

export interface ConnectorStatus {
  provider: ConnectorProvider;
  connected: boolean;
  external_account_label: string | null;
  connected_at: string | null;
}

export async function fetchConnectors(): Promise<ConnectorStatus[]> {
  return apiFetch<ConnectorStatus[]>("/v1/connectors");
}

export function connectUrl(provider: ConnectorProvider): string {
  return `${API_URL}/v1/connectors/${provider}/connect`;
}

export async function disconnectConnector(provider: ConnectorProvider): Promise<void> {
  await apiFetch<void>(`/v1/connectors/${provider}`, { method: "DELETE" });
}
