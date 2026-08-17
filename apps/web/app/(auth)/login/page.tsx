import { loginUrl } from "@/lib/api";

const PROVIDERS = [
  { id: "github", label: "GitHub" },
  { id: "slack", label: "Slack" },
  { id: "google", label: "Google" },
] as const;

export default function LoginPage() {
  return (
    <div className="flex flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-neutral-200 px-6 py-3 text-xs tracking-[0.2em] text-neutral-500 uppercase">
        <span>Relay</span>
        <span>Sign in</span>
      </div>

      <div className="mx-auto grid w-full max-w-5xl flex-1 items-center gap-10 px-6 py-16 md:grid-cols-[1.3fr_1fr]">
        <div>
          <p className="max-w-sm text-sm leading-relaxed text-neutral-600">
            A shared context engine across GitHub, Slack, and Jira — one retrieval engine,
            queried three different ways.
          </p>
          <h1 className="font-serif text-brand mt-4 text-[5rem] leading-[0.85] tracking-tight sm:text-[7.5rem]">
            Relay
          </h1>
        </div>

        <div className="flex flex-col gap-3">
          <div className="bg-brand text-brand-foreground rounded-md p-5">
            <p className="text-sm font-medium leading-relaxed">
              This only identifies you — connecting GitHub, Slack, and Jira for data access
              happens separately, once you&apos;re signed in.
            </p>
          </div>

          {PROVIDERS.map((provider) => (
            <a
              key={provider.id}
              href={loginUrl(provider.id)}
              className="flex h-12 items-center justify-center rounded-md border border-neutral-900 text-sm font-medium text-neutral-900 transition-colors hover:bg-neutral-900 hover:text-white"
            >
              Continue with {provider.label}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
