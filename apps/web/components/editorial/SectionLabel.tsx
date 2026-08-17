const TONES = {
  muted: "text-muted",
  brand: "text-brand",
  ink: "text-ink",
  paper: "text-paper-white/60",
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
