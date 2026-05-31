/**
 * CSS-only port of react-bits GradientText (terminal density).
 * @see https://github.com/DavidHDev/react-bits/tree/main/src/content/TextAnimations/GradientText
 */
import type { ReactNode } from "react";
import "./GradientText.css";

interface GradientTextProps {
  children: ReactNode;
  className?: string;
  /** CSS gradient stops for animated text fill */
  gradient?: string;
}

const DEFAULT_GRADIENT =
  "linear-gradient(90deg, #2dd4bf, #38bdf8, #a78bfa, #2dd4bf)";

export function GradientText({
  children,
  className = "",
  gradient = DEFAULT_GRADIENT,
}: GradientTextProps) {
  return (
    <span
      className={`rb-gradient-text${className ? ` ${className}` : ""}`}
      style={{ backgroundImage: gradient }}
    >
      {children}
    </span>
  );
}
