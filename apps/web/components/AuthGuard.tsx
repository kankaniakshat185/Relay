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

    fetchCurrentUser().then((result) => {
      if (cancelled) return;
      if (result === null) {
        router.replace("/login");
      } else {
        setUser(result);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [router]);

  if (user === "loading" || user === null) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-neutral-500">Checking session…</p>
      </div>
    );
  }

  return <CurrentUserContext.Provider value={user}>{children}</CurrentUserContext.Provider>;
}
