import type { ReactNode } from "react";

/** A full red editorial block with typography inside — the reference's
 * defining move. Never a rounded "info card"; sharp corners, red as
 * composition, not decoration. */
export function RedPanel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`bg-brand text-paper-white ${className}`}>{children}</div>;
}
