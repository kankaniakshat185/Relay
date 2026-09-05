import Link from "next/link";

import { LogoMark } from "./LogoMark";
import { SectionLabel } from "./SectionLabel";

const CONNECTIONS = ["GitHub", "Slack", "Jira"];
const PRODUCT = [
  { label: "Search", href: "/search" },
  { label: "Archaeology", href: "/archaeology" },
  { label: "Who to Ask", href: "/who-to-ask" },
  { label: "Flaky Tests", href: "/flaky-tests" },
  { label: "Notes", href: "/notes" },
  { label: "Weekly Digest", href: "/weekly-digest" },
  { label: "Incident Correlation", href: "/incident-correlation" },
  { label: "Decision Debt", href: "/decision-debt" },
  { label: "Connections", href: "/connections" },
];
const ELSEWHERE = [
  { label: "GitHub", href: "https://github.com/kankaniakshat185/Relay", icon: "github" as const },
  { label: "Portfolio", href: "https://akshatkankani.vercel.app", icon: "globe" as const },
];

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 .5C5.73.5.5 5.73.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.88-1.54-3.88-1.54-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.23-1.28-5.23-5.7 0-1.26.45-2.29 1.19-3.09-.12-.29-.52-1.46.11-3.04 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 5.79 0c2.2-1.49 3.17-1.18 3.17-1.18.64 1.58.24 2.75.12 3.04.74.8 1.19 1.83 1.19 3.09 0 4.43-2.69 5.41-5.25 5.69.41.36.78 1.06.78 2.15 0 1.55-.01 2.8-.01 3.18 0 .31.21.67.8.56A10.52 10.52 0 0 0 23.5 12C23.5 5.73 18.27.5 12 .5z" />
    </svg>
  );
}

function GlobeMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className={className}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

const ELSEWHERE_ICONS = { github: GitHubMark, globe: GlobeMark };

function FooterColumn({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <SectionLabel tone="inverse">{label}</SectionLabel>
      <div className="mt-4 flex flex-col gap-2">{children}</div>
    </div>
  );
}

/** Editorial ending, not a generic SaaS footer — closes with a giant,
 * intentionally cropped wordmark. Dark-on-light in light mode; in dark
 * mode it flips to light-on-dark instead of staying a fixed dark island
 * — the point of this section is contrast against the surrounding page,
 * which means following the theme, not resisting it. Every color below
 * is a theme-aware role token (`ink`/`paper`/`brand`), not `--color-
 * paper-white` or Tailwind's own `white` — those are fixed, and would go
 * invisible against this footer's own background once it flips. */
export function Footer() {
  return (
    <footer className="bg-ink text-paper mt-24">
      <div className="mx-auto max-w-[1600px] px-6 py-16 sm:px-10">
        <div className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-4">
          <div className="col-span-2 sm:col-span-1">
            <div className="flex items-center gap-2">
              <LogoMark className="footer-logo-mark h-6 w-6" />
              <p className="font-serif text-2xl">Relay</p>
            </div>
            <p className="text-paper/50 mt-2 text-xs leading-relaxed">
              Correlates commits, discussions, and tickets into one answer — so the story behind a
              line of code doesn&apos;t live in someone&apos;s memory.
            </p>
          </div>

          <FooterColumn label="Connections">
            {CONNECTIONS.map((source) => (
              <span key={source} className="text-paper/80 text-sm">
                {source}
              </span>
            ))}
          </FooterColumn>

          <FooterColumn label="Product">
            {PRODUCT.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-paper/80 hover:text-paper text-sm transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </FooterColumn>

          <FooterColumn label="Elsewhere">
            {ELSEWHERE.map((item) => {
              const Icon = ELSEWHERE_ICONS[item.icon];
              return (
                <a
                  key={item.href}
                  href={item.href}
                  target="_blank"
                  rel="noreferrer"
                  className="text-paper/80 hover:text-paper flex items-center gap-2 text-sm transition-colors"
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </a>
              );
            })}
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
