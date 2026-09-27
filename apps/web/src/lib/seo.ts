import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";

export const SITE_NAME = "MangaTranslate AI";
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

type PublicPage = "home" | "pricing" | "features" | "faq" | "terms" | "privacy" | "copyright" | "login" | "register";

/** Title, description, canonical and OpenGraph for a public page. */
export async function pageMetadata(page: PublicPage, path: string): Promise<Metadata> {
  const t = await getTranslations("meta");
  const locale = await getLocale();
  const title = t(`${page}.title`);
  const description = t(`${page}.description`);
  return {
    title: page === "home" ? { absolute: title } : title,
    description,
    alternates: { canonical: path },
    openGraph: { title, description, url: path, siteName: SITE_NAME, type: "website", locale: locale === "vi" ? "vi_VN" : "en_US" },
    twitter: { card: "summary", title, description },
  };
}

export const NO_INDEX: Metadata = { robots: { index: false, follow: false } };
