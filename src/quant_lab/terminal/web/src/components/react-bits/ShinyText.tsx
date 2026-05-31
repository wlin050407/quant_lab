/**
 * CSS-only port of react-bits ShinyText (no motion/react).
 * @see https://github.com/DavidHDev/react-bits/tree/main/src/content/TextAnimations/ShinyText
 */
import "./ShinyText.css";

interface ShinyTextProps {
  text: string;
  className?: string;
  disabled?: boolean;
}

export function ShinyText({ text, className = "", disabled = false }: ShinyTextProps) {
  return (
    <span
      className={`rb-shiny-text${disabled ? " rb-shiny-text--static" : ""}${className ? ` ${className}` : ""}`}
    >
      {text}
    </span>
  );
}
