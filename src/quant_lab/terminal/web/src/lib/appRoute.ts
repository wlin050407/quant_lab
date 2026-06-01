/** Hash routes: #/ · #/index · #/stock */

export type AppRoute = "home" | "index" | "stock";

export function parseAppRoute(hash: string = window.location.hash): AppRoute {
  const path = hash.replace(/^#/, "").replace(/^\//, "").split("?")[0]?.toLowerCase() ?? "";
  if (path === "index" || path.startsWith("index/")) return "index";
  if (path === "stock" || path.startsWith("stock/")) return "stock";
  return "home";
}

export function navigateTo(route: AppRoute): void {
  const next = route === "home" ? "#/" : `#/${route}`;
  if (window.location.hash !== next) {
    window.location.hash = next;
  }
}

export function routeLabel(route: AppRoute): string {
  if (route === "index") return "Index · 0DTE";
  if (route === "stock") return "Equity";
  return "Home";
}
