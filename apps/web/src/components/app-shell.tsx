"use client";

import { Coins, LogOut, Settings, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useUser } from "@/components/user-context";
import { api, isAdmin } from "@/lib/api";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: ReactNode }) {
  const t = useTranslations("nav");
  const { user } = useUser();
  const pathname = usePathname();
  const router = useRouter();
  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/login");
  }
  const links = [
    { href: "/dashboard", label: t("dashboard") },
    { href: "/jobs", label: t("jobs") },
    { href: "/jobs/new", label: t("newJob") },
    { href: "/billing", label: t("billing") },
    { href: "/usage", label: t("usage") },
    { href: "/settings", label: t("settings") },
    ...(isAdmin(user) ? [{ href: "/admin", label: t("admin") }] : []),
  ];
  // Longest matching prefix is the current section (so /jobs/new does not also mark /jobs).
  const current = links
    .filter((l) => pathname === l.href || pathname.startsWith(`${l.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-4">
          <Logo href="/dashboard" />
          <div className="ml-auto flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href="/billing" aria-label={t("creditsLabel", { count: user.credits })}>
                <Coins aria-hidden />
                {user.credits}
              </Link>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label={t("account")}>
                  <UserRound aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="truncate">{user.email}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link href="/settings">
                    <Settings aria-hidden />
                    {t("settings")}
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => logout()}>
                  <LogOut aria-hidden />
                  {t("logout")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <nav aria-label={t("main")} className="mx-auto w-full max-w-7xl overflow-x-auto px-2">
          <ul className="flex gap-1 text-sm">
            {links.map((l) => (
              <li key={l.href}>
                <Link
                  href={l.href}
                  aria-current={current === l.href ? "page" : undefined}
                  className={cn(
                    "inline-block border-b-2 border-transparent px-3 py-2 whitespace-nowrap text-muted-foreground hover:text-foreground",
                    current === l.href && "border-primary text-foreground",
                  )}
                >
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" className="flex flex-1 flex-col">
        {children}
      </main>
    </>
  );
}
