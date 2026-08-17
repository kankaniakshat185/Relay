"use client";

import { useEffect, useState } from "react";

import {
  type ConnectorProvider,
  type ConnectorStatus,
  connectUrl,
  disconnectConnector,
  fetchConnectors,
} from "@/lib/connectors";

const PROVIDER_LABELS: Record<ConnectorProvider, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
};

const PROVIDER_DESCRIPTIONS: Record<ConnectorProvider, string> = {
  github: "Recent pull requests across repos you have access to.",
  slack: "Recent messages in channels the Relay bot has been added to.",
  jira: "Recent issues from your first accessible Jira Cloud site.",
};

export default function ConnectionsPage() {
  const [statuses, setStatuses] = useState<ConnectorStatus[] | "loading">("loading");
  const [pendingProvider, setPendingProvider] = useState<ConnectorProvider | null>(null);

  useEffect(() => {
    fetchConnectors().then(setStatuses);
  }, []);

  async function handleDisconnect(provider: ConnectorProvider) {
    setPendingProvider(provider);
    await disconnectConnector(provider);
    setStatuses(await fetchConnectors());
    setPendingProvider(null);
  }

  return (
    <div className="max-w-3xl">
      <p className="text-xs tracking-[0.2em] text-neutral-400 uppercase">Connections</p>
      <h1 className="font-serif mt-2 text-4xl text-neutral-900">Data access</h1>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-600">
        Separate from signing in — each connection here grants Relay read-only access to build
        the context engine. Revocable independently, any time.
      </p>

      <div className="mt-10 grid gap-px overflow-hidden rounded-md border border-neutral-200 bg-neutral-200 sm:grid-cols-3">
        {statuses === "loading"
          ? Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-40 animate-pulse bg-white" />
            ))
          : statuses.map((status) => (
              <div key={status.provider} className="flex flex-col justify-between bg-white p-5">
                <div>
                  <p className="font-serif text-xl text-neutral-900">
                    {PROVIDER_LABELS[status.provider]}
                  </p>
                  <p className="mt-2 text-xs leading-relaxed text-neutral-500">
                    {PROVIDER_DESCRIPTIONS[status.provider]}
                  </p>
                  {status.connected && status.external_account_label && (
                    <p className="text-brand mt-3 text-xs font-medium">
                      Connected — {status.external_account_label}
                    </p>
                  )}
                </div>

                {status.connected ? (
                  <button
                    onClick={() => handleDisconnect(status.provider)}
                    disabled={pendingProvider === status.provider}
                    className="mt-5 h-10 rounded-md border border-neutral-300 text-sm font-medium text-neutral-700 transition-colors hover:border-neutral-900 hover:text-neutral-900 disabled:opacity-50"
                  >
                    {pendingProvider === status.provider ? "Disconnecting…" : "Disconnect"}
                  </button>
                ) : (
                  <a
                    href={connectUrl(status.provider)}
                    className="bg-brand text-brand-foreground mt-5 flex h-10 items-center justify-center rounded-md text-sm font-medium"
                  >
                    Connect
                  </a>
                )}
              </div>
            ))}
      </div>
    </div>
  );
}
