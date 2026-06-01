import { BrandMark } from "../components/BrandMark";
import { BrandWordmark } from "../components/BrandWordmark";
import { IconMoon, IconSun } from "../components/Icons";
import { useTheme } from "../hooks/useTheme";
import { navigateTo } from "../lib/appRoute";

const FOCUS = [
  "Strike-level GEX and dealer positioning factors",
  "Pin aggregation and intraday session replay",
  "Reproducible playbook blocks for SPXW research",
] as const;

const ROUTES = [
  {
    id: "index" as const,
    title: "Index 0DTE",
    desc: "EoD and live chain snapshots, GEX heatmap, pin deck, Pin Playbook.",
    status: "Active",
    primary: true,
  },
  {
    id: "stock" as const,
    title: "Single Equity",
    desc: "Per-ticker positioning and earnings-window context.",
    status: "Preview",
    primary: false,
  },
];

export function HomePage() {
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="gate">
      <div className="gate__shell">
        <header className="gate__nav">
          <a className="gate__brand" href="#/" aria-label="Quantlab home">
            <BrandMark size={28} />
            <BrandWordmark tagline="Research workspace" />
          </a>

          <div className="gate__nav-actions">
            <button
              type="button"
              className="gate__icon-btn"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Light mode" : "Dark mode"}
            >
              {theme === "dark" ? <IconSun /> : <IconMoon />}
            </button>
            <button type="button" className="gate__link-btn" onClick={() => navigateTo("index")}>
              <span className="gate__link-btn-full">Open workspace</span>
              <span className="gate__link-btn-short" aria-hidden>
                Open
              </span>
            </button>
          </div>
        </header>

        <main className="gate__main">
          <section className="gate__intro" aria-labelledby="gate-title">
            <p className="gate__eyebrow">Research · SPX 0DTE · Dealer positioning</p>

            <h1 id="gate-title" className="gate__title">
              Model dealer gamma before the session reprices.
            </h1>

            <p className="gate__blurb">
              quant_lab is a research workspace for SPXW intraday studies. Current work centers on chain
              quality, positioning factors on SPY proxy history, and tools to inspect pin risk before
              execution—not a signal feed or brokerage layer.
            </p>

            <ul className="gate__focus">
              {FOCUS.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>

            <div className="gate__actions">
              <button type="button" className="gate__btn gate__btn--primary" onClick={() => navigateTo("index")}>
                Continue to Index workspace
              </button>
            </div>
          </section>

          <section className="gate__routes" aria-labelledby="gate-routes-title">
            <h2 id="gate-routes-title" className="gate__routes-label">
              Workspaces
            </h2>

            <ul className="gate__route-list">
              {ROUTES.map((route) => (
                <li key={route.id}>
                  <button
                    type="button"
                    className={`gate__route${route.primary ? " gate__route--primary" : ""}`}
                    onClick={() => navigateTo(route.id)}
                  >
                    <span className="gate__route-status">{route.status}</span>
                    <span className="gate__route-title">{route.title}</span>
                    <span className="gate__route-desc">{route.desc}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </main>

        <footer className="gate__foot">
          <span>quant_lab</span>
          <span aria-hidden>·</span>
          <span>Phase 0–1 · data &amp; positioning factors</span>
        </footer>
      </div>
    </div>
  );
}
