import { createContext } from "react";

import type { Locale } from "../lib/locale";

export interface LocaleContextValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  toggleLocale: () => void;
  isZh: boolean;
}

export const LocaleContext = createContext<LocaleContextValue | null>(null);
