/** Thin 1px rules that define the grid — see globals.css design tokens.
 * Not decoration around individual components; use these to divide
 * sections, nav, footer, feature rows. */

export function Rule({ className = "" }: { className?: string }) {
  return <div className={`border-line border-t ${className}`} />;
}

export function VerticalRule({ className = "" }: { className?: string }) {
  return <div className={`border-line border-l ${className}`} />;
}
