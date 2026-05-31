/**
 * Vendored from react-bits (MIT + Commons Clause)
 * @see https://github.com/DavidHDev/react-bits/tree/main/src/content/Components/SpotlightCard
 */
import { useRef, type ReactNode } from "react";
import "./SpotlightCard.css";

interface SpotlightCardProps {
  children: ReactNode;
  className?: string;
  spotlightColor?: string;
  id?: string;
}

export function SpotlightCard({
  children,
  className = "",
  spotlightColor = "rgba(20, 184, 166, 0.06)",
  id,
}: SpotlightCardProps) {
  const divRef = useRef<HTMLDivElement>(null);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = divRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mouse-x", `${e.clientX - rect.left}px`);
    el.style.setProperty("--mouse-y", `${e.clientY - rect.top}px`);
    el.style.setProperty("--spotlight-color", spotlightColor);
  };

  return (
    <div
      ref={divRef}
      id={id}
      className={`card-spotlight card-spotlight--terminal${className ? ` ${className}` : ""}`}
      onMouseMove={handleMouseMove}
    >
      {children}
    </div>
  );
}
