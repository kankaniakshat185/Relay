const TONES = {
  muted: "text-muted",
  brand: "text-brand",
  ink: "text-ink",
  paper: "text-paper-white/60",
  /** For labels sitting on the footer's own `bg-ink text-paper` surface —
   * theme-aware (`text-paper`, not the fixed `paper-white`), since that
   * surface itself flips light/dark with the theme instead of staying a
   * fixed island. */
  inverse: "text-paper/60",
} as const;

interface SectionLabelProps {
  children: React.ReactNode;
  tone?: keyof typeof TONES;
  className?: string;
}

/** Small uppercase tracked metadata label — "CONNECTIONS", "LIVE",
 * "SIGNED IN". Carries as much of the visual identity as the display
 * type does; use it, don't reach for a plain <p>. */
export function SectionLabel({ children, tone = "muted", className = "" }: SectionLabelProps) {
  return (
    <p className={`text-xs font-medium tracking-[0.2em] uppercase ${TONES[tone]} ${className}`}>
      {children}
    </p>
  );
}
