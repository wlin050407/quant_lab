import { useEffect, useState } from "react";

import { parseAppRoute, type AppRoute } from "./lib/appRoute";
import { HomePage } from "./pages/HomePage";
import { IndexTerminalApp } from "./pages/IndexTerminalApp";
import { StockTerminalPage } from "./pages/StockTerminalPage";

function readRoute(): AppRoute {
  return parseAppRoute();
}

export default function App() {
  const [route, setRoute] = useState<AppRoute>(() => readRoute());

  useEffect(() => {
    const onHash = () => setRoute(readRoute());
    window.addEventListener("hashchange", onHash);
    if (!window.location.hash) {
      window.location.replace("#/");
    }
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  if (route === "index") return <IndexTerminalApp />;
  if (route === "stock") return <StockTerminalPage />;
  return <HomePage />;
}
