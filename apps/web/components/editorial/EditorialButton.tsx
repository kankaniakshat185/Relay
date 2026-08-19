import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

/** Rectangular editorial controls — sharp corners, 1px border, tracked
 * uppercase label, arrow that shifts on hover. Never a rounded SaaS
 * button. Two exports because OAuth/connect links are real navigations
 * (`<a href>`), while disconnect/submit actions are `<button>`. */

const BASE =
  "group inline-flex items-center justify-between gap-3 border px-5 py-3 text-xs font-medium tracking-[0.15em] uppercase transition-colors disabled:pointer-events-none disabled:opacity-50";

const VARIANTS = {
  default: "border-ink text-ink hover:bg-ink hover:text-paper",
  brand: "border-brand bg-brand text-paper-white hover:border-ink hover:bg-ink hover:text-paper",
} as const;

function Arrow() {
  return (
    <span aria-hidden className="transition-transform group-hover:translate-x-1">
      →
    </span>
  );
}

interface EditorialLinkButtonProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  variant?: keyof typeof VARIANTS;
  children: ReactNode;
}

export function EditorialLinkButton({
  children,
  className = "",
  variant = "default",
  ...props
}: EditorialLinkButtonProps) {
  return (
    <a className={`${BASE} ${VARIANTS[variant]} ${className}`} {...props}>
      <span>{children}</span>
      <Arrow />
    </a>
  );
}

interface EditorialButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANTS;
  children: ReactNode;
}

export function EditorialButton({
  children,
  className = "",
  variant = "default",
  ...props
}: EditorialButtonProps) {
  return (
    <button className={`${BASE} ${VARIANTS[variant]} ${className}`} {...props}>
      <span>{children}</span>
      <Arrow />
    </button>
  );
}
