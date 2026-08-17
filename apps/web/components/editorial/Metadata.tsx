const TONES = {
  muted: "text-muted",
  paper: "text-paper-white/60",
} as const;

/** A single row of small tracked metadata, dot-separated —
 * "GITHUB · PULL_REQUEST · OCTOCAT · JAN 15". Filters out falsy items so
 * callers don't need to build the join logic themselves. */
export function Metadata({
  items,
  tone = "muted",
  className = "",
}: {
  items: Array<string | null | undefined>;
  tone?: keyof typeof TONES;
  className?: string;
}) {
  const visible = items.filter((item): item is string => Boolean(item && item.trim()));
  if (visible.length === 0) return null;

  return (
    <p className={`text-[11px] font-medium tracking-[0.1em] uppercase ${TONES[tone]} ${className}`}>
      {visible.join("   ·   ")}
    </p>
  );
}
