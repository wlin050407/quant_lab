import iconSrc from "../assets/brand/quantlab-icon.png";

interface BrandMarkProps {
  size?: number;
  className?: string;
}

/** Rounded shell matches TopBar favicon tile (26.5% radius). */
export function BrandMark({ size = 34, className = "" }: BrandMarkProps) {
  const radius = Math.max(8, Math.round(size * 0.265));

  return (
    <span
      className={`brand-icon-shell${className ? ` ${className}` : ""}`}
      style={{ width: size, height: size, borderRadius: radius }}
      aria-hidden
    >
      <img
        src={iconSrc}
        alt=""
        className="brand-icon-img"
        style={{ borderRadius: radius }}
        draggable={false}
      />
    </span>
  );
}
