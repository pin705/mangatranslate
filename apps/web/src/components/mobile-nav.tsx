"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

export function MobileNav({ links, syncAccount }: { links: { href: string; label: string }[]; syncAccount: boolean }) {
  const t = useTranslations("nav");
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label={t("menu")}>
          <Menu aria-hidden />
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="p-6">
        <SheetTitle>{t("menu")}</SheetTitle>
        <nav aria-label={t("main")} className="mt-4 flex flex-col gap-3">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="text-base hover:underline" onClick={() => setOpen(false)}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="mt-6 sm:hidden">
          <LanguageSwitcher syncAccount={syncAccount} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
