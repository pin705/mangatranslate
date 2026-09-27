import { cookies } from "next/headers";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { LanguageSwitcher } from "@/components/language-switcher";
import { MobileNav } from "@/components/mobile-nav";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/logo";
import { SITE_NAME } from "@/lib/seo";

export async function SiteHeader() {
  const t = await getTranslations("nav");
  const loggedIn = (await cookies()).has("mt_session");
  const links = [
    { href: "/features", label: t("features") },
    { href: "/pricing", label: t("pricing") },
    { href: "/faq", label: t("faq") },
  ];
  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-4">
        <Logo />
        <nav aria-label={t("main")} className="hidden gap-5 text-sm md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="text-muted-foreground hover:text-foreground">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <div className="hidden sm:block">
            <LanguageSwitcher syncAccount={loggedIn} />
          </div>
          {loggedIn ? (
            <Button asChild size="sm">
              <Link href="/dashboard">{t("dashboard")}</Link>
            </Button>
          ) : (
            <>
              <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
                <Link href="/login">{t("login")}</Link>
              </Button>
              <Button asChild size="sm">
                <Link href="/register">{t("register")}</Link>
              </Button>
            </>
          )}
          <MobileNav links={loggedIn ? links : [...links, { href: "/login", label: t("login") }]} syncAccount={loggedIn} />
        </div>
      </div>
    </header>
  );
}

export async function SiteFooter() {
  const t = await getTranslations("footer");
  const links = [
    { href: "/features", label: t("features") },
    { href: "/pricing", label: t("pricing") },
    { href: "/faq", label: t("faq") },
    { href: "/terms", label: t("terms") },
    { href: "/privacy", label: t("privacy") },
    { href: "/copyright", label: t("copyright") },
  ];
  return (
    <footer className="mt-auto border-t">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-6 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>{t("rights", { year: new Date().getFullYear(), name: SITE_NAME })}</p>
        <nav aria-label={t("label")} className="flex flex-wrap gap-x-4 gap-y-2">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-foreground">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
