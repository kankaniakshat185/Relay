import Link from "next/link";

import { type LinkedSource, annotateHref } from "@/lib/notes";

/** "+ Annotate" — opens the Notes composer pre-filled with a reference
 * back to `title`/`url`. Used anywhere this app links out to a real
 * GitHub/Slack/Jira item (Search, Archaeology, Who Should I Ask) so
 * jotting a note down never means losing the item you were looking at.
 * Not shown for `source: "notes"` items — annotating a note with another
 * note isn't a case this supports (see ADR 0021). */
export function AnnotateLink({
  source,
  url,
  title,
  className = "",
}: {
  source: LinkedSource;
  url: string;
  title: string;
  className?: string;
}) {
  return (
    <Link
      href={annotateHref(source, url, title)}
      className={`text-muted hover:text-ink shrink-0 text-xs font-medium tracking-[0.15em] uppercase transition-colors ${className}`}
    >
      + Annotate
    </Link>
  );
}
