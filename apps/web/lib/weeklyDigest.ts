import { apiFetch } from "./api";
import type { ItemCitation, LlmProvider, LlmUnavailableReason } from "./synthesis";

export interface WeeklyDigestResponse {
  used_llm: boolean;
  llm_unavailable_reason: LlmUnavailableReason | null;
  digest: string | null;
  sources: ItemCitation[];
}

export interface WeeklyDigestOptions {
  days?: number;
  useLlm?: boolean;
  llmProvider?: LlmProvider;
  apiKey?: string;
}

export async function runWeeklyDigest(
  options: WeeklyDigestOptions = {}
): Promise<WeeklyDigestResponse> {
  return apiFetch<WeeklyDigestResponse>("/v1/weekly-digest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      days: options.days ?? 7,
      use_llm: options.useLlm ?? false,
      llm_provider: options.llmProvider ?? "openai",
      api_key: options.apiKey || null,
    }),
  });
}

export interface ParsedDigestSections {
  shipped: string;
  stillInMotion: string;
  unresolved: string;
}

const SECTION_HEADERS = ["SHIPPED", "STILL IN MOTION", "UNRESOLVED"] as const;

/** The digest prompt (`features/weekly_digest/service.py`) asks the model
 * for exactly these three labels, each alone on its own line, in order —
 * this is the frontend half of that contract. Only trusts the structure
 * when all three appear, in the right order, each on its own line;
 * otherwise returns null so the caller falls back to rendering the whole
 * string as one passage rather than mislabeling prose that didn't
 * actually follow the format. */
export function parseDigestSections(digest: string): ParsedDigestSections | null {
  const lines = digest.split("\n");
  const indexByHeader = new Map<string, number>();

  lines.forEach((line, i) => {
    const trimmed = line.trim().toUpperCase();
    if (
      (SECTION_HEADERS as readonly string[]).includes(trimmed) &&
      !indexByHeader.has(trimmed)
    ) {
      indexByHeader.set(trimmed, i);
    }
  });

  const found = SECTION_HEADERS.map((header) => indexByHeader.get(header));
  if (found.some((i) => i === undefined)) return null;
  const [shippedAt, motionAt, unresolvedAt] = found as number[];
  if (!(shippedAt < motionAt && motionAt < unresolvedAt)) return null;

  const section = (start: number, end: number) => lines.slice(start + 1, end).join("\n").trim();

  return {
    shipped: section(shippedAt, motionAt),
    stillInMotion: section(motionAt, unresolvedAt),
    unresolved: section(unresolvedAt, lines.length),
  };
}
