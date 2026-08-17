"use client";

import { useCurrentUser } from "./AuthGuard";
import { logout } from "@/lib/auth";
import { useRouter } from "next/navigation";

const NAV_ITEMS = [
  { label: "Search", phase: 1 },
  { label: "Archaeology", phase: 2 },
  { label: "Who to Ask", phase: 2 },
  { label: "Flaky Tests", phase: 3 },
  { label: "Dependency Alerts", phase: 4 },
] as const;

export function DashboardNav() {
  const user = useCurrentUser();
  const router = useRouter();

  return (
    <header className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
      <div className="flex items-center gap-8">
        <span className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Relay
        </span>
        <nav className="flex items-center gap-4">
          {NAV_ITEMS.map((item) => (
            <span
              key={item.label}
              title={`Ships in Phase ${item.phase}`}
              className="cursor-not-allowed text-sm text-zinc-400 dark:text-zinc-600"
            >
              {item.label}
            </span>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-zinc-600 dark:text-zinc-400">{user.display_name}</span>
        <button
          onClick={async () => {
            await logout();
            router.replace("/login");
          }}
          className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
