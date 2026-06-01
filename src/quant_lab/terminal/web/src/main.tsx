import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { LocaleProvider } from "./providers/LocaleProvider";
import { initTheme } from "./lib/theme";
import { applyLocale, readStoredLocale } from "./lib/locale";
import "./styles/design-tokens.css";
import "./styles/brand.css";
import "./styles/terminal.css";
import "./styles/panels.css";
import "./styles/instrument-strip.css";
import "./styles/heatmap-stage.css";
import "./styles/scrollbars.css";
import "./styles/polish.css";
import "./styles/loading.css";
import "./styles/exposure-profile.css";
import "./styles/charts.css";
import "./styles/panel-sections.css";
import "./styles/trace-layout.css";
import "./styles/pin-panel.css";
import "./styles/home.css";
import "./styles/equity.css";
import "./styles/index-terminal-mobile.css";
import "./styles/themes.css";
import "./styles/strike-plot-light.css";

initTheme();
applyLocale(readStoredLocale());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <App />
      </LocaleProvider>
    </QueryClientProvider>
  </StrictMode>,
);
