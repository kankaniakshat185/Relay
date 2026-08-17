import { apiFetch, ApiError } from "./api";

export interface CurrentUser {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
}

/** Returns the current user, or `null` if there's no valid session. */
export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  try {
    return await apiFetch<CurrentUser>("/v1/auth/me");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      return null;
    }
    throw err;
  }
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/v1/auth/logout", { method: "POST" });
}
