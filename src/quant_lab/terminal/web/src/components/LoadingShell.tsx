import { BrandMark } from "./BrandMark";
import { BrandWordmark } from "./BrandWordmark";

export function LoadProgressBar({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <div className="load-progress" role="progressbar" aria-label="Loading snapshot">
      <div className="load-progress-bar" />
    </div>
  );
}

export function LoadingShell() {
  return (
    <main className="boot-shell" aria-busy="true" aria-label="Loading terminal">
      <div className="boot-shell-inner">
        <BrandMark size={52} className="boot-brand-mark" />
        <BrandWordmark tagline="Loading positioning snapshot…" />
        <div className="boot-shell-track">
          <div className="boot-shell-fill" />
        </div>
      </div>
    </main>
  );
}
