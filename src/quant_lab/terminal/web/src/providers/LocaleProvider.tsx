import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { LocaleContext } from "../hooks/localeContext";
import { applyLocale, LOCALE_STORAGE_KEY, readStoredLocale, type Locale } from "../lib/locale";

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => readStoredLocale());

  useEffect(() => {
    applyLocale(locale);
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
  }, []);

  const toggleLocale = useCallback(() => {
    setLocaleState((prev) => (prev === "zh" ? "en" : "zh"));
  }, []);

  const value = useMemo(
    () => ({ locale, setLocale, toggleLocale, isZh: locale === "zh" }),
    [locale, setLocale, toggleLocale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}
