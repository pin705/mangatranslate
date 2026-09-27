"use client";

import { useTranslations } from "next-intl";

/** Localised name for an API language value ("Chinese" → "Tiếng Trung"); unknown values pass through. */
export function useLangName() {
  const t = useTranslations("languages");
  return (lang: string) => (t.has(lang as "Chinese") ? t(lang as "Chinese") : lang);
}
