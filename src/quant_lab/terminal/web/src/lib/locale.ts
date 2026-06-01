export type Locale = "en" | "zh";

export const LOCALE_STORAGE_KEY = "quantlab-locale";

export function readStoredLocale(): Locale {
  if (typeof window === "undefined") return "en";
  try {
    const raw = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return raw === "zh" ? "zh" : "en";
  } catch {
    return "en";
  }
}

export function applyLocale(locale: Locale): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  document.documentElement.dataset.locale = locale;
}
