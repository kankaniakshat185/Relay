import Image from "next/image";

/** The geometric icon mark, cropped from the source logo (logo.jpg at the
 * repo root) and keyed to a transparent PNG — see the crop/key script in
 * the Phase-1-redesign session if this ever needs regenerating from a new
 * source file. Solid `--relay-black` on a transparent background, so it
 * only reads correctly on light/off-white backgrounds by default.
 *
 * `invert` flips it to solid white via a CSS filter (`brightness-0
 * invert` — forces pure black first, then inverts, so it's not at the
 * mercy of the source PNG's slightly-off-black anti-aliased edges) for
 * use on dark surfaces like the footer, rather than shipping a second
 * PNG asset for one color variant. */
export function LogoMark({
  className = "h-5 w-5",
  invert = false,
}: {
  className?: string;
  invert?: boolean;
}) {
  return (
    <Image
      src="/logo-mark.png"
      alt=""
      width={444}
      height={396}
      priority
      className={`object-contain ${invert ? "brightness-0 invert" : ""} ${className}`}
    />
  );
}
