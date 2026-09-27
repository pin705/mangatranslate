"use client";

import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useId } from "react";
import { api } from "@/lib/api";
import { setLocaleCookie } from "@/lib/utils";

/** Sets the NEXT_LOCALE cookie; when logged in also saves the preference on the account (best effort). */
export function LanguageSwitcher({ syncAccount = false }: { syncAccount?: boolean }) {
  const t = useTranslations("nav");
  const locale = useLocale();
  const router = useRouter();
  const id = useId();

  async function change(next: string) {
    setLocaleCookie(next);
    if (syncAccount) await api("/me", { method: "PATCH", json: { locale: next } }).catch(() => undefined);
    router.refresh();
  }

  return (
    <>
      <label htmlFor={id} className="sr-only">
        {t("language")}
      </label>
      <select
        id={id}
        value={locale}
        onChange={(e) => change(e.target.value)}
        className="h-8 rounded-lg border bg-background px-2 text-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <option value="vi">{t("languageNames.vi")}</option>
        <option value="en">{t("languageNames.en")}</option>
      </select>
    </>
  );
}
