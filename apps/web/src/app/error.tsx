"use client";

import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

// Unexpected render errors: generic message only (no stack traces for users).
export default function Error({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations("errors");
  return (
    <main id="main" className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center gap-3 px-4 py-16 text-center">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <p className="text-muted-foreground">{t("generic")}</p>
      <Button onClick={reset}>{t("retry")}</Button>
    </main>
  );
}
