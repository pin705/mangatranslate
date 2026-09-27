"use client";

import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function AdminHeading({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function useFmt() {
  const format = useFormatter();
  return {
    date: (s: string | null) => (s ? format.dateTime(new Date(s), { dateStyle: "medium", timeStyle: "short" }) : "–"),
    day: (s: string) => format.dateTime(new Date(s), { dateStyle: "medium", timeZone: "UTC" }),
    num: (n: number) => format.number(n),
    usd: (n: number, digits = 2) => format.number(n, { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits }),
    money: (n: number, currency: string) => format.number(n, { style: "currency", currency, maximumFractionDigits: currency === "VND" ? 0 : 2 }),
  };
}

/** Status filter; "" means all. */
export function StatusFilter<T extends string>({
  value,
  onChange,
  options,
  label,
  optionLabel,
}: {
  value: T | "";
  onChange: (v: T | "") => void;
  options: readonly T[];
  label: string;
  optionLabel: (v: T) => string;
}) {
  const t = useTranslations("common");
  return (
    <Select value={value || "__all"} onValueChange={(v) => onChange(v === "__all" ? "" : (v as T))}>
      <SelectTrigger aria-label={label} className="w-44">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__all">{t("all")}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {optionLabel(o)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Admin endpoints documented loosely as "list" may return an array or {items,total}. */
export const asArray = <T,>(d: T[] | { items: T[] } | undefined): T[] | undefined => (d === undefined ? d : Array.isArray(d) ? d : d.items);
