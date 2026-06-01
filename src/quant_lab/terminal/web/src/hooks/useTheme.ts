import { useCallback, useEffect, useState } from "react";

import {
  applyTheme,
  readStoredTheme,
  THEME_STORAGE_KEY,
  type ThemeMode,
} from "../lib/theme";

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(() => readStoredTheme());

  useEffect(() => {
    applyTheme(theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = useCallback((next: ThemeMode) => {
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  return { theme, setTheme, toggleTheme, isLight: theme === "light" };
}
