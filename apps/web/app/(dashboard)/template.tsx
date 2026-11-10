import { ViewTransition } from "react";

// `template.tsx` remounts between `layout.tsx` and `page.tsx` on every
// navigation (unlike layout.tsx, which persists) — that remount is what
// gives `<ViewTransition>` an exit/enter pair to animate between. See
// node_modules/next/dist/docs/01-app/02-guides/view-transitions.md.
// DashboardNav/Footer live in layout.tsx, outside this subtree, so they
// never take part — no separate "anchor the header" CSS needed here.
export default function DashboardTemplate({ children }: { children: React.ReactNode }) {
  return (
    <ViewTransition enter="page-crossfade" exit="page-crossfade">
      {children}
    </ViewTransition>
  );
}
