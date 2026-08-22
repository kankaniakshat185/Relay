/**
 * Fetch wrapper for the Relay backend.
 *
 * Every call goes to this app's own origin under `/api` — `next.config.ts`'s
 * `rewrites()` proxies it server-side to the real backend (ADR 0024). The
 * browser never talks to the backend's domain directly, which is what
 * makes the session cookie (minted during the OAuth callback, itself
 * reached through this same proxy) genuinely first-party: no cross-site
 * request means no `SameSite`/Safari-ITP problem to work around. Next.js
 * server components still can't read the cookie via `next/headers` (it's
 * minted by the backend, not this app), so auth-aware calls stay
 * client-side — that part hasn't changed.
 */

export const API_URL = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    // FastAPI's standard error shape is `{"detail": "..."}` — a human
    // sentence when the backend raised `HTTPException(status, "...")`
    // deliberately (e.g. the sync cooldown message), not just a status
    // code. Falls back to the generic message if the body isn't JSON or
    // doesn't have `detail` (a raw 500, a proxy error page, etc.).
    let message = `${init?.method ?? "GET"} ${path} failed: ${response.status}`;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {
      // Not JSON — keep the generic message.
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function loginUrl(provider: "github" | "slack" | "google"): string {
  return `${API_URL}/v1/auth/${provider}/login`;
}
