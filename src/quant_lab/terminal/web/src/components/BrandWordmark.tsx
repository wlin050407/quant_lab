interface BrandWordmarkProps {
  className?: string;
  /** Show tagline under wordmark */
  tagline?: string;
}

/** Dark-terminal wordmark: quant (light) + lab (teal→mint gradient) */
export function BrandWordmark({ className = "", tagline }: BrandWordmarkProps) {
  return (
    <div className={`brand-wordmark-block${className ? ` ${className}` : ""}`}>
      <div className="brand-wordmark" aria-label="Quant Lab">
        <span className="brand-wordmark-quant">quant</span>
        <span className="brand-wordmark-lab">lab</span>
      </div>
      {tagline ? <div className="brand-tagline">{tagline}</div> : null}
    </div>
  );
}
