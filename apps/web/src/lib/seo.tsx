import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";

// Both are inlined at build time (NEXT_PUBLIC_*).
export const SITE_NAME = process.env.NEXT_PUBLIC_SITE_NAME || "MangaTranslate AI";
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000").replace(/\/$/, "");
export const absUrl = (path: string) => `${SITE_URL}${path === "/" ? "" : path}`;

type MetaKey =
  | "home" | "pricing" | "features" | "faq" | "terms" | "privacy" | "copyright"
  | "login" | "register"; // keys of messages `meta.*`; add here together with vi/en.json entries

type SeoInput = { title: string; description: string; path: string; absoluteTitle?: boolean; type?: "website" | "article" };

/** Title, description, canonical, OpenGraph and Twitter card for any public page. */
export async function seo({ title, description, path, absoluteTitle, type = "website" }: SeoInput): Promise<Metadata> {
  const locale = await getLocale();
  return {
    title: absoluteTitle ? { absolute: title } : title,
    description,
    alternates: { canonical: path },
    openGraph: { title, description, url: path, siteName: SITE_NAME, type, locale: locale === "vi" ? "vi_VN" : "en_US" },
    twitter: { card: "summary_large_image", title, description },
  };
}

/** seo() with the title/description taken from messages `meta.{page}`. */
export async function pageMetadata(page: MetaKey, path: string): Promise<Metadata> {
  const t = await getTranslations("meta");
  return seo({
    title: t(`${page}.title`, { site: SITE_NAME }),
    description: t(`${page}.description`, { site: SITE_NAME }),
    path,
    absoluteTitle: page === "home",
  });
}

export const NO_INDEX: Metadata = { robots: { index: false, follow: false } };

/** Replace {site} in raw (non-ICU) message content such as t.raw() arrays. */
export function withSite<T>(value: T): T {
  return JSON.parse(JSON.stringify(value).replaceAll("{site}", SITE_NAME.replace(/["\\]/g, "\\$&"))) as T;
}

/** Structured data. `<` is escaped so the payload cannot close the script element. */
export function JsonLd({ data }: { data: object | object[] }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }} />;
}

export const breadcrumbLd = (items: { name: string; path: string }[]) => ({
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  itemListElement: items.map((it, i) => ({ "@type": "ListItem", position: i + 1, name: it.name, item: absUrl(it.path) })),
});

export const faqLd = (items: { q: string; a: string }[]) => ({
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: items.map((it) => ({ "@type": "Question", name: it.q, acceptedAnswer: { "@type": "Answer", text: it.a } })),
});
