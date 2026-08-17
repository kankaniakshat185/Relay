"use client";

import { useCurrentUser } from "@/components/AuthGuard";

export default function DashboardHome() {
  const user = useCurrentUser();

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
        Welcome, {user.display_name}
      </h1>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        You&apos;re signed in — this is the login flow only. Connecting GitHub, Slack, and Jira
        for data access is a separate step that ships with the Context Searcher in Phase 1.
      </p>

      <div className="mt-8 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Roadmap</h2>
        <ul className="mt-3 space-y-2 text-sm text-zinc-500 dark:text-zinc-400">
          <li>Phase 1 — Connections + Context Searcher</li>
          <li>Phase 2 — Codebase Archaeology + Who Should I Ask</li>
          <li>Phase 3 — Flaky Test Investigator</li>
          <li>Phase 4 — Dependency Alert Bot</li>
        </ul>
      </div>
    </div>
  );
}
