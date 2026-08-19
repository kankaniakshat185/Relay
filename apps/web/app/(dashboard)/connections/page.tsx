"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { EditorialButton, EditorialLinkButton } from "@/components/editorial/EditorialButton";
import { Metadata } from "@/components/editorial/Metadata";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import {
  type ConnectorProvider,
  type ConnectorStatus,
  connectUrl,
  disconnectConnector,
  fetchConnectors,
  syncConnector,
} from "@/lib/connectors";

const PROVIDER_LABELS: Record<ConnectorProvider, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
};

const PROVIDER_DESCRIPTIONS: Record<ConnectorProvider, string> = {
  github: "Repository context — recent pull requests and commit messages across repos you have access to.",
  slack: "Workspace context — recent messages in channels the Relay bot has joined.",
  jira: "Issue context — recent issues from your first accessible Jira Cloud site.",
};

// A real sync (fetch + ingest + embed) typically takes 15-40s — poll
// rather than assume, so "Syncing…" reflects when it actually finished,
// not a guessed duration. Stops on its own after SYNC_POLL_TIMEOUT_MS
// even if `last_synced_at` never moves (a failed job, a dead worker —
// see the retro this feature came out of), so the button never gets
// stuck disabled forever.
const SYNC_POLL_INTERVAL_MS = 3000;
const SYNC_POLL_TIMEOUT_MS = 90_000;

function formatSyncedAt(iso: string | null): string {
  if (!iso) return "Never synced";
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "Synced just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Synced ${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Synced ${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `Synced ${days}d ago`;
}

// Module-level, not defined inside the component — `Date.now()` here is
// an event-driven side effect (started from a click, not render), but
// react-hooks' purity check can't tell the difference between "defined
// in render" and "only invoked from an event handler" for a function
// declared inside the component body, so it flags any impure call
// reachable from there regardless of nesting. Living outside the
// component sidesteps that, more honestly than an eslint-disable would.
async function pollUntilSynced(
  provider: ConnectorProvider,
  before: string | null,
  startedAt: number,
  onUpdate: (statuses: ConnectorStatus[]) => void,
  onFinished: () => void
): Promise<void> {
  const fresh = await fetchConnectors();
  onUpdate(fresh);
  const updated = fresh.find((s) => s.provider === provider)?.last_synced_at ?? null;
  const finished = updated !== null && updated !== before;
  if (finished || Date.now() - startedAt > SYNC_POLL_TIMEOUT_MS) {
    onFinished();
    return;
  }
  setTimeout(() => {
    void pollUntilSynced(provider, before, startedAt, onUpdate, onFinished);
  }, SYNC_POLL_INTERVAL_MS);
}

function startSyncPolling(
  provider: ConnectorProvider,
  before: string | null,
  onUpdate: (statuses: ConnectorStatus[]) => void,
  onFinished: () => void
): void {
  const startedAt = Date.now();
  setTimeout(() => {
    void pollUntilSynced(provider, before, startedAt, onUpdate, onFinished);
  }, SYNC_POLL_INTERVAL_MS);
}

export default function ConnectionsPage() {
  const [statuses, setStatuses] = useState<ConnectorStatus[] | "loading">("loading");
  const [pendingProvider, setPendingProvider] = useState<ConnectorProvider | null>(null);
  const [syncingProviders, setSyncingProviders] = useState<Set<ConnectorProvider>>(new Set());
  const [syncErrors, setSyncErrors] = useState<Partial<Record<ConnectorProvider, string>>>({});

  useEffect(() => {
    fetchConnectors().then(setStatuses);
  }, []);

  async function handleDisconnect(provider: ConnectorProvider) {
    setPendingProvider(provider);
    await disconnectConnector(provider);
    setStatuses(await fetchConnectors());
    setPendingProvider(null);
  }

  // Shared by both the per-provider "Sync now" buttons and "Sync all
  // connected" — each provider's request/poll/error is independent, so
  // one already in cooldown (or one that fails) doesn't block the others
  // when triggered together.
  async function syncOne(provider: ConnectorProvider) {
    setSyncErrors((prev) => {
      const next = { ...prev };
      delete next[provider];
      return next;
    });
    const before = Array.isArray(statuses)
      ? (statuses.find((s) => s.provider === provider)?.last_synced_at ?? null)
      : null;

    try {
      await syncConnector(provider);
    } catch (err) {
      setSyncErrors((prev) => ({
        ...prev,
        [provider]: err instanceof ApiError ? err.message : "Couldn't reach the server — try again.",
      }));
      return;
    }

    setSyncingProviders((prev) => new Set(prev).add(provider));
    startSyncPolling(provider, before, setStatuses, () => {
      setSyncingProviders((prev) => {
        const next = new Set(prev);
        next.delete(provider);
        return next;
      });
    });
  }

  function handleSync(provider: ConnectorProvider) {
    void syncOne(provider);
  }

  function handleSyncAll() {
    if (!Array.isArray(statuses)) return;
    for (const status of statuses) {
      if (status.connected) void syncOne(status.provider);
    }
  }

  const connectedCount = Array.isArray(statuses) ? statuses.filter((s) => s.connected).length : 0;

  return (
    <div>
      <SectionLabel tone="brand">Connections</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        Data access
      </DisplayHeading>
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Separate from signing in — each connection here grants Relay read-only access to build
        the context engine. Revocable independently, any time.
      </p>

      {connectedCount > 0 && (
        <button
          type="button"
          onClick={handleSyncAll}
          disabled={syncingProviders.size >= connectedCount}
          className="border-brand text-brand hover:bg-brand hover:text-paper-white mt-8 border px-3 py-1.5 text-xs font-medium tracking-[0.1em] uppercase transition-colors disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
        >
          {syncingProviders.size > 0
            ? `Syncing ${syncingProviders.size} of ${connectedCount}…`
            : "Sync all connected →"}
        </button>
      )}

      <Rule className="mt-16" />

      <div className="grid grid-cols-1 md:grid-cols-3">
        {statuses === "loading"
          ? Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className={`border-line h-72 animate-pulse border-b py-10 ${
                  i !== 0 ? "md:border-l md:pl-8" : ""
                } ${i !== 2 ? "md:pr-8" : ""}`}
              />
            ))
          : statuses.map((status, i) => (
              <div
                key={status.provider}
                className={`border-line flex flex-col justify-between border-b py-10 ${
                  i !== 0 ? "md:border-l md:pl-8" : ""
                } ${i !== statuses.length - 1 ? "md:pr-8" : ""}`}
              >
                <div>
                  <DisplayHeading as="h2" size="md" className="text-ink">
                    {PROVIDER_LABELS[status.provider]}
                  </DisplayHeading>
                  <p className="text-muted mt-4 text-sm leading-relaxed">
                    {PROVIDER_DESCRIPTIONS[status.provider]}
                  </p>
                  {status.connected && (
                    <div className="mt-6">
                      <SectionLabel tone="brand">Connected</SectionLabel>
                      <Metadata
                        items={[
                          status.external_account_label,
                          syncingProviders.has(status.provider)
                            ? "Syncing…"
                            : formatSyncedAt(status.last_synced_at),
                        ]}
                        className="mt-2"
                      />
                      <button
                        type="button"
                        onClick={() => handleSync(status.provider)}
                        disabled={syncingProviders.has(status.provider)}
                        className="text-muted hover:text-ink mt-3 text-xs font-medium tracking-[0.15em] uppercase transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {syncingProviders.has(status.provider) ? "Syncing" : "Sync now →"}
                      </button>
                      {syncErrors[status.provider] && (
                        <p className="text-brand mt-2 text-xs">{syncErrors[status.provider]}</p>
                      )}
                    </div>
                  )}
                </div>

                {status.connected ? (
                  <EditorialButton
                    onClick={() => handleDisconnect(status.provider)}
                    disabled={pendingProvider === status.provider}
                    className="mt-10 w-fit"
                  >
                    {pendingProvider === status.provider ? "Disconnecting" : "Disconnect"}
                  </EditorialButton>
                ) : (
                  <EditorialLinkButton
                    href={connectUrl(status.provider)}
                    variant="brand"
                    className="mt-10 w-fit"
                  >
                    Connect
                  </EditorialLinkButton>
                )}
              </div>
            ))}
      </div>
    </div>
  );
}
