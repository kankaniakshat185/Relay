import Image from "next/image";

/** The geometric icon mark, cropped from the source logo (logo.jpg at the
 * repo root) and keyed to a transparent PNG — see the crop/key script in
 * the Phase-1-redesign session if this ever needs regenerating from a new
 * source file. Solid `--relay-black`, so it only reads correctly on
 * light/off-white backgrounds — not used on the dark footer. */
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
