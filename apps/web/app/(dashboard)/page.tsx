"use client";

import { useCurrentUser } from "@/components/AuthGuard";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { EditorialLinkButton } from "@/components/editorial/EditorialButton";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";

const FEATURES = [
  {
    n: "01",
    title: "Connections + Context Search",
    status: "live" as const,
    span: "md:col-span-7",
  },
  {
    n: "02",
    title: "Codebase Archaeology + Who Should Ask",
    status: "upcoming" as const,
    span: "md:col-span-5",
  },
  {
    n: "03",
    title: "Flaky Test Investigator",
    status: "upcoming" as const,
    span: "md:col-span-4",
  },
  {
    n: "04",
    title: "Dependency Alert Bot",
    status: "upcoming" as const,
    span: "md:col-span-8",
  },
];

export default function DashboardHome() {
  const user = useCurrentUser();

  return (
    <div>
      <SectionLabel tone="muted">Signed in as {user.display_name}</SectionLabel>
      <SectionLabel tone="brand" className="mt-6">
        Relay / Context Engine
      </SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3 max-w-4xl">
        Your engineering context, connected.
      </DisplayHeading>

      <EditorialLinkButton href="/connections" variant="brand" className="mt-8 w-fit">
        Connect your accounts
      </EditorialLinkButton>

      <Rule className="mt-20" />

      <div className="grid grid-cols-1 gap-x-8 md:grid-cols-12">
        {FEATURES.map((feature, i) => (
          <div
            key={feature.n}
            className={`border-line border-b py-10 ${feature.span} ${i % 2 === 0 ? "md:border-r md:pr-8" : "md:pl-8"}`}
          >
            <p className="font-serif text-brand text-6xl sm:text-7xl">{feature.n}</p>
            <DisplayHeading as="h2" size="md" className="text-ink mt-4 max-w-sm">
              {feature.title}
            </DisplayHeading>
            <p
              className={`mt-6 text-xs font-medium tracking-[0.2em] uppercase ${
                feature.status === "live" ? "text-brand" : "text-muted"
              }`}
            >
              {feature.status}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
