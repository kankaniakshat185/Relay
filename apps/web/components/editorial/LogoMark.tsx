import Image from "next/image";

/** The geometric icon mark, cropped from the source logo (logo.jpg at the
 * repo root) and keyed to a transparent PNG — see the crop/key script in
 * the Phase-1-redesign session if this ever needs regenerating from a new
 * source file. Solid `--relay-black` on a transparent background — needs
 * an inverting filter whenever it sits on a dark surface, and since dark
 * mode means *every* surface it appears on is theme-aware (not a fixed
 * light/dark split), that inversion is a CSS class keyed to the theme,
 * not a boolean prop here. Two surfaces, two classes, opposite logic:
 * `.nav-logo-mark` (DashboardNav, login) sits on the page's own
 * `bg-paper` — light in light mode (no filter needed), dark in dark mode
 * (needs inverting). `.footer-logo-mark` (Footer) sits on the footer's
 * `bg-ink`, which is the *reverse* — dark in light mode (needs
 * inverting), light in dark mode (no filter needed). Both defined in
 * globals.css, next to the token definitions they depend on. */
export function LogoMark({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <Image
      src="/logo-mark.png"
      alt=""
      width={444}
      height={396}
      priority
      className={`object-contain ${className}`}
    />
  );
}
