"use client";

import { useEffect, useState } from "react";

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
    <div>
      <SectionLabel tone="brand">Connections</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        Data access
      </DisplayHeading>
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Separate from signing in — each connection here grants Relay read-only access to build
        the context engine. Revocable independently, any time.
      </p>

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
                        items={[status.external_account_label]}
                        className="mt-2"
                      />
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
