interface KeyboardHintsProps {
  focusMode: boolean;
  symbol: string;
}

export function KeyboardHints({ focusMode, symbol }: KeyboardHintsProps) {
  return (
    <footer className="keyboard-hints" aria-label="Keyboard shortcuts">
      <span className="kbd-hint">
        <kbd>←</kbd><kbd>→</kbd> date
      </span>
      <span className="kbd-hint">
        <kbd>G</kbd> GEX <kbd>V</kbd> VEX <kbd>C</kbd> compare
      </span>
      {symbol === "^SPX" ? (
        <span className="kbd-hint">
          <kbd>[</kbd><kbd>]</kbd> session time
        </span>
      ) : null}
      <span className="kbd-hint">
        <kbd>1</kbd> single <kbd>3</kbd> trinity
      </span>
      <span className="kbd-hint">
        <kbd>T</kbd> live today
      </span>
      <span className="kbd-hint">
        <kbd>F</kbd> {focusMode ? "exit focus" : "heatmap focus"}
      </span>
      <span className="kbd-hint kbd-hint--muted">research only · not advice</span>
    </footer>
  );
}
