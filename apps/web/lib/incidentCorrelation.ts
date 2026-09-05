import { apiFetch } from "./api";
import type { CommitEntry } from "./archaeology";
import type { ItemCitation, LlmProvider, LlmUnavailableReason } from "./synthesis";

export interface IncidentCorrelationResponse {
  used_llm: boolean;
  llm_unavailable_reason: LlmUnavailableReason | null;
  narrative: string | null;
  sources: ItemCitation[];
  /** v2 — the same `TimelineEntry` shape Archaeology renders (backend
   * re-exports the identical class, see ADR 0026), filtered to the
   * incident window. Empty when no file was named, not just omitted. */
  file_trace: CommitEntry[];
}

export interface IncidentCorrelationOptions {
  incidentAt: string;
  windowBeforeHours?: number;
  windowAfterHours?: number;
  owner?: string;
  repo?: string;
  ref?: string;
  filePath?: string;
  useLlm?: boolean;
  llmProvider?: LlmProvider;
  apiKey?: string;
}

export async function runIncidentCorrelation(
  options: IncidentCorrelationOptions
): Promise<IncidentCorrelationResponse> {
  return apiFetch<IncidentCorrelationResponse>("/v1/incident-correlation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      incident_at: options.incidentAt,
      window_before_hours: options.windowBeforeHours ?? 48,
      window_after_hours: options.windowAfterHours ?? 2,
      owner: options.owner || null,
      repo: options.repo || null,
      ref: options.ref || null,
      file_path: options.filePath || null,
      use_llm: options.useLlm ?? false,
      llm_provider: options.llmProvider ?? "openai",
      api_key: options.apiKey || null,
    }),
  });
}
