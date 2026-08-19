import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { LogoMark } from "@/components/editorial/LogoMark";
import { RedPanel } from "@/components/editorial/RedPanel";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ThemeToggle } from "@/components/ThemeToggle";
import { loginUrl } from "@/lib/api";

const PROVIDERS = [
  { id: "github", label: "GitHub" },
  { id: "slack", label: "Slack" },
  { id: "google", label: "Google" },
] as const;

export default function LoginPage() {
  return (
    <div className="flex flex-1 flex-col">
      <div className="border-line flex h-16 items-center justify-between border-b px-6 sm:h-18 sm:px-10">
        <span className="flex items-center gap-2">
          <LogoMark className="nav-logo-mark h-7 w-7" />
          <span className="font-serif text-ink text-3xl">Relay</span>
        </span>
        <div className="flex items-center gap-5">
          <ThemeToggle />
          <SectionLabel>Sign in</SectionLabel>
        </div>
      </div>

      <div className="mx-auto grid w-full max-w-[1600px] flex-1 grid-cols-1 gap-x-10 gap-y-16 px-6 py-16 sm:px-10 md:grid-cols-12 md:items-center md:py-0">
        <div className="md:col-span-7">
          <SectionLabel tone="brand">Relay / Context Engine</SectionLabel>
          <p className="text-muted mt-4 max-w-sm text-sm leading-relaxed">
            A shared context engine across GitHub, Slack, and Jira — one retrieval engine,
            queried three different ways.
          </p>
          <DisplayHeading size="hero" className="text-ink -ml-1 mt-2">
            Relay
          </DisplayHeading>
        </div>

        <div className="flex flex-col gap-3 md:col-span-5">
          <RedPanel className="p-6">
            <SectionLabel tone="paper">This only identifies you —</SectionLabel>
            <p className="mt-3 text-sm leading-relaxed">
              Connecting GitHub, Slack, and Jira for data access happens separately, once
              you&apos;re signed in.
            </p>
          </RedPanel>

          <div className="border-line flex flex-col border">
            {PROVIDERS.map((provider, i) => (
              <a
                key={provider.id}
                href={loginUrl(provider.id)}
                className={`group hover:bg-ink hover:text-paper flex h-14 items-center justify-between px-5 text-sm font-medium tracking-wide text-ink transition-colors ${
                  i !== 0 ? "border-line border-t" : ""
                }`}
              >
                <span>Continue with {provider.label}</span>
                <span aria-hidden className="transition-transform group-hover:translate-x-1">
                  →
                </span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
