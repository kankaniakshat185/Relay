import { loginUrl } from "@/lib/api";

const PROVIDERS = [
  { id: "github", label: "Continue with GitHub" },
  { id: "slack", label: "Continue with Slack" },
  { id: "google", label: "Continue with Google" },
] as const;

export default function LoginPage() {
  return (
    <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Sign in to Relay</h1>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        This only identifies you — connecting GitHub, Slack, and Jira for data access happens
        separately, after you&apos;re signed in.
      </p>

      <div className="mt-6 flex flex-col gap-3">
        {PROVIDERS.map((provider) => (
          <a
            key={provider.id}
            href={loginUrl(provider.id)}
            className="flex h-11 items-center justify-center rounded-md border border-zinc-300 text-sm font-medium text-zinc-800 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-800"
          >
            {provider.label}
          </a>
        ))}
      </div>
    </div>
  );
}
