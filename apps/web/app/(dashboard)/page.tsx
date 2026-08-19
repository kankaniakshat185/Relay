"use client";

import Link from "next/link";

import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { EditorialLinkButton } from "@/components/editorial/EditorialButton";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";

const FEATURES = [
  {
    n: "01",
    title: "Connections + Context Search",
    description:
      "Connect GitHub, Slack, and Jira, then ask a question — Relay retrieves and synthesizes a source-attributed answer across all three.",
    status: "live" as const,
    href: "/search",
    span: "md:col-span-7",
  },
  {
    n: "02",
    title: "Codebase Archaeology",
    description:
      "Pick a file. Relay traces its git blame back through each commit to the pull request that introduced it, the Jira ticket it closed, and the Slack discussion happening at the time.",
    status: "live" as const,
    href: "/archaeology",
    span: "md:col-span-5",
  },
  {
    n: "03",
    title: "Who Should I Ask",
    description:
      "Ranks everyone who's touched a file or directory by recency or frequency — including reviewers who never committed a line.",
    status: "live" as const,
    href: "/who-to-ask",
    span: "md:col-span-6",
  },
  {
    n: "04",
    title: "Flaky Test Investigator",
    description:
      "Tracks each workflow's pass/fail history and flags what looks flaky rather than genuinely broken — a same-commit re-run succeeding is the clearest sign.",
    status: "live" as const,
    href: "/flaky-tests",
    span: "md:col-span-6",
  },
  {
    n: "05",
    title: "Dependency Alert Bot",
    description:
      "Watches dependency version bumps, parses changelogs, and cross-references against actual usage in the codebase.",
    status: "upcoming" as const,
    href: null,
    span: "md:col-span-12",
  },
];

export default function DashboardHome() {
  return (
    <div>
      <SectionLabel tone="brand">Relay / Context Engine</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3 max-w-4xl">
        Your engineering context, connected.
      </DisplayHeading>

      <EditorialLinkButton href="/connections" variant="brand" className="mt-8 w-fit">
        Connect your accounts
      </EditorialLinkButton>

      <Rule className="mt-20" />

      <div className="grid grid-cols-1 gap-x-8 md:grid-cols-12">
        {FEATURES.map((feature, i) => {
          const isFullWidth = feature.span === "md:col-span-12";
          const content = (
            <>
              <p className="font-serif text-brand text-6xl sm:text-7xl">{feature.n}</p>
              <DisplayHeading as="h2" size="md" className="text-ink mt-4 max-w-sm">
                {feature.title}
              </DisplayHeading>
              <p className="text-muted mt-3 max-w-sm text-sm leading-relaxed">{feature.description}</p>
            </>
          );
          const className = `border-line group block border-b py-10 ${feature.span} ${
            isFullWidth ? "" : i % 2 === 0 ? "md:border-r md:pr-8" : "md:pl-8"
          }`;

          return feature.href ? (
            <Link key={feature.n} href={feature.href} className={`${className} transition-opacity hover:opacity-70`}>
              {content}
            </Link>
          ) : (
            <div key={feature.n} className={className}>
              {content}
            </div>
          );
        })}
      </div>
    </div>
  );
}
