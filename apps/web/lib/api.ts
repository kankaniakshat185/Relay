/**
 * Fetch wrapper for the Relay backend.
 *
 * The session cookie is set on the *backend's* domain (it's minted during
 * the OAuth callback, which is a backend route) — not the frontend's. That
 * means Next.js server components can't read it via `next/headers`, so
 * auth-aware calls happen client-side with `credentials: "include"`, which
 * does carry the cookie on cross-origin requests to the API's own domain.
 * If that stops being good enough (e.g. we want SSR'd authenticated pages),
 * the fix is a BFF proxy under `app/api/`, not a same-site cookie hack.
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
