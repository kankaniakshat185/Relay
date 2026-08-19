import { API_URL, apiFetch } from "./api";

export type ConnectorProvider = "github" | "slack" | "jira";

export interface ConnectorStatus {
  provider: ConnectorProvider;
  connected: boolean;
  external_account_label: string | null;
  connected_at: string | null;
  last_synced_at: string | null;
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

/** Throws `ApiError` (status 429) if a sync was requested too recently —
 * `apiFetch` surfaces the backend's own message ("Synced recently — try
 * again in Ns."), so callers can show `err.message` directly rather than
 * writing their own copy. */
export async function syncConnector(provider: ConnectorProvider): Promise<void> {
  await apiFetch<void>(`/v1/connectors/${provider}/sync`, { method: "POST" });
}
