"use client";

import { useTranslations } from "next-intl";
import { describeError } from "@/lib/api";

export function useErrorText() {
  const t = useTranslations("errors");
  return (e: unknown) => describeError(e, t);
}
