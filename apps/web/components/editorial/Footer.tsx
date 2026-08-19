import Link from "next/link";

import { SectionLabel } from "./SectionLabel";

const SOURCES = ["GitHub", "Slack", "Jira"];
const PRODUCT = [
  { label: "Search", href: "/search" },
  { label: "Archaeology", href: "/archaeology" },
  { label: "Who to Ask", href: "/who-to-ask" },
  { label: "Connections", href: "/connections" },
];
const ROADMAP = ["Flaky Tests", "Dependency Alerts"];

function FooterColumn({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <SectionLabel tone="paper">{label}</SectionLabel>
      <div className="mt-4 flex flex-col gap-2">{children}</div>
    </div>
  );
}

/** Editorial ending, not a generic SaaS footer — closes with a giant,
 * intentionally cropped wordmark. */
export function Footer() {
  return (
    <footer className="bg-ink text-paper-white mt-24">
      <div className="mx-auto max-w-[1600px] px-6 py-16 sm:px-10">
        <div className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-4">
          <div className="col-span-2 sm:col-span-1">
            <p className="font-serif text-2xl">Relay</p>
            <p className="text-paper-white/50 mt-2 text-xs leading-relaxed">
              A shared context engine across GitHub, Slack, and Jira.
            </p>
          </div>

          <FooterColumn label="Sources">
            {SOURCES.map((source) => (
              <span key={source} className="text-sm text-white/80">
                {source}
              </span>
            ))}
          </FooterColumn>

          <FooterColumn label="Product">
            {PRODUCT.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-sm text-white/80 transition-colors hover:text-white"
              >
                {item.label}
              </Link>
            ))}
          </FooterColumn>

          <FooterColumn label="Roadmap">
            {ROADMAP.map((item) => (
              <span key={item} className="text-sm text-white/40">
                {item}
              </span>
            ))}
          </FooterColumn>
        </div>
      </div>

      <div className="overflow-hidden">
        <p className="font-serif text-brand -mb-[0.14em] translate-y-[0.14em] pl-4 text-[20vw] leading-none select-none">
          Relay
        </p>
      </div>
    </footer>
  );
}
