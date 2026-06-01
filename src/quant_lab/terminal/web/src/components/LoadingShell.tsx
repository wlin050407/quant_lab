import { BrandMark } from "./BrandMark";
import { BrandWordmark } from "./BrandWordmark";

export function LoadProgressBar({ active, ariaLabel = "Loading snapshot" }: { active: boolean; ariaLabel?: string }) {
  if (!active) return null;
  return (
    <div className="load-progress" role="progressbar" aria-label={ariaLabel}>
      <div className="load-progress-bar" />
    </div>
  );
}

export function LoadingShell({ tagline = "Loading positioning snapshot…" }: { tagline?: string }) {
  return (
    <main className="boot-shell" aria-busy="true" aria-label={tagline}>
      <div className="boot-shell-inner">
        <BrandMark size={52} className="boot-brand-mark" />
        <BrandWordmark tagline={tagline} />
        <div className="boot-shell-track">
          <div className="boot-shell-fill" />
        </div>
      </div>
    </main>
  );
}
