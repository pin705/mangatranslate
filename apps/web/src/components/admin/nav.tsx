"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

const SECTIONS = ["", "users", "jobs", "payments", "credits", "providers", "costs", "system", "audit"] as const;

export function AdminNav() {
  const t = useTranslations("admin.nav");
  const pathname = usePathname();
  return (
    <nav aria-label={t("label")} className="shrink-0 overflow-x-auto border-b lg:w-48 lg:border-r lg:border-b-0">
      <ul className="flex gap-1 p-2 text-sm lg:flex-col">
        {SECTIONS.map((s) => {
          const href = s ? `/admin/${s}` : "/admin";
          const active = s ? pathname.startsWith(href) : pathname === "/admin";
          return (
            <li key={s}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn("block rounded-md px-3 py-1.5 whitespace-nowrap hover:bg-muted", active && "bg-muted font-medium")}
              >
                {t(s || "overview")}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
