import type { ElementType, ReactNode } from "react";

/** Centralized type scale — the only place heading sizes are defined, so
 * "how big is big" stays a system decision, not a per-page guess. `hero`
 * is deliberately allowed to approach viewport width (clamp, not a fixed
 * breakpoint jump) — oversized type is a graphic element here, not just
 * a heading. */
const SIZES = {
  hero: "text-[clamp(4rem,13vw,13rem)] leading-[0.85]",
  xl: "text-[clamp(2.75rem,7vw,6.5rem)] leading-[0.9]",
  lg: "text-[clamp(2.25rem,5vw,4rem)] leading-[0.95]",
  md: "text-[clamp(1.5rem,3vw,2.25rem)] leading-tight",
} as const;

interface DisplayHeadingProps {
  as?: ElementType;
  size?: keyof typeof SIZES;
  className?: string;
  children: ReactNode;
}

export function DisplayHeading({
  as: Tag = "h1",
  size = "lg",
  className = "",
  children,
}: DisplayHeadingProps) {
  return <Tag className={`font-serif tracking-tight ${SIZES[size]} ${className}`}>{children}</Tag>;
}
