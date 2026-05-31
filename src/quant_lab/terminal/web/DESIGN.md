# Terminal UI — design sources

| Source | How we use it |
|--------|----------------|
| [GSAP](https://github.com/greensock/GSAP) | Charts, `AnimatedPrice`, Trinity column stagger |
| [react-bits](https://github.com/DavidHDev/react-bits) | `SpotlightCard` on ladder / right rail |
| [impeccable](https://github.com/pbakaus/impeccable) | `npm run design:audit` |
| [awesome-design-md](https://github.com/VoltAgent/awesome-design-md) | `--surface-*`, type scale |

## Stylesheet order (single cascade)

`design-tokens` → `brand` → `terminal` (layout, heatmap rows, controls) → `panels` → `instrument-strip` → `heatmap-stage` → `scrollbars` → `polish` (shell overrides) → `loading` → `exposure-profile`

`terminal-v2.css` removed — rules live in `polish.css` + feature CSS files.

## Layout

1. **InstrumentStrip** — one bar for instrument + data meta
2. **Heatmap stage** — chart-first, floating toolbar, GSAP Trinity stagger
3. **Ladder + Right rail** — supporting panels
