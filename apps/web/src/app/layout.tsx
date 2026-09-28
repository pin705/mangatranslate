import type { Metadata, Viewport } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";
import { SITE_NAME, SITE_URL } from "@/lib/seo";
import "./globals.css";

// Every page depends on the locale cookie and/or live API data: never prerender at build time.
export const dynamic = "force-dynamic";

// Long-form namespaces are rendered on the server only; keep them out of the client payload.
const SERVER_ONLY = new Set(["legal", "features", "faq", "home", "meta"]);

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return {
    metadataBase: new URL(SITE_URL),
    title: { default: t("home.title", { site: SITE_NAME }), template: `%s · ${SITE_NAME}` },
    description: t("home.description", { site: SITE_NAME }),
    applicationName: SITE_NAME,
    openGraph: { siteName: SITE_NAME, type: "website" },
    twitter: { card: "summary_large_image" },
  };
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const t = await getTranslations("nav");
  const messages = Object.fromEntries(Object.entries(await getMessages()).filter(([k]) => !SERVER_ONLY.has(k)));
  return (
    <html lang={locale} className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only z-50 rounded-md bg-background px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:ring-2 focus:ring-ring"
        >
          {t("skip")}
        </a>
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
