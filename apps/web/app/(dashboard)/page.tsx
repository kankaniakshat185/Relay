"use client";

import Link from "next/link";

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
    href: "/search",
    span: "md:col-span-7",
  },
  {
    n: "02",
    title: "Codebase Archaeology",
    status: "live" as const,
    href: "/archaeology",
    span: "md:col-span-5",
  },
  {
    n: "03",
    title: "Who Should I Ask",
    status: "live" as const,
    href: "/who-to-ask",
    span: "md:col-span-6",
  },
  {
    n: "04",
    title: "Flaky Test Investigator",
    status: "upcoming" as const,
    href: null,
    span: "md:col-span-6",
  },
  {
    n: "05",
    title: "Dependency Alert Bot",
    status: "upcoming" as const,
    href: null,
    span: "md:col-span-12",
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
        {FEATURES.map((feature, i) => {
          const isFullWidth = feature.span === "md:col-span-12";
          const content = (
            <>
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
