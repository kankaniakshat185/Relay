"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { type CurrentUser, fetchCurrentUser } from "@/lib/auth";

const CurrentUserContext = createContext<CurrentUser | null>(null);

export function useCurrentUser(): CurrentUser {
  const user = useContext(CurrentUserContext);
  if (user === null) {
    throw new Error("useCurrentUser() called outside an authenticated <AuthGuard>");
  }
  return user;
}

/**
 * Client-side route guard for the (dashboard) route group. Checks the
 * session against the backend on mount and redirects to /login if it's
 * missing or invalid — see lib/api.ts for why this can't be done in a
 * server component yet.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null | "loading">("loading");

  useEffect(() => {
    let cancelled = false;

    fetchCurrentUser()
      .then((result) => {
        if (cancelled) return;
        if (result === null) {
          router.replace("/login");
        } else {
          setUser(result);
        }
      })
      .catch((err: unknown) => {
        // A clean "not logged in" (401) already resolves to `null` above,
        // never throws — this only catches the unexpected case (a network
        // failure, a CORS rejection, the API being unreachable). Treating
        // it the same as "not authenticated" means a real backend problem
        // sends the user to a working login page instead of leaving this
        // screen stuck on "Checking session…" forever, which is what an
        // unhandled rejection here used to do (found live: a CORS
        // misconfiguration between a freshly deployed frontend/backend
        // pair surfaced as an infinite spinner, not a visible error).
        if (cancelled) return;
        console.error(err);
        router.replace("/login");
      });

    return () => {
      cancelled = true;
    };
  }, [router]);

  if (user === "loading" || user === null) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-muted text-xs tracking-[0.15em] uppercase">Checking session…</p>
      </div>
    );
  }

  return <CurrentUserContext.Provider value={user}>{children}</CurrentUserContext.Provider>;
}
