import { getTranslations } from "next-intl/server";
import { pageMetadata } from "@/lib/seo";

export const generateMetadata = () => pageMetadata("faq", "/faq");

export default async function FaqPage() {
  const t = await getTranslations("faq");
  const items = t.raw("items") as { q: string; a: string }[];
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
      <div className="mt-8 divide-y rounded-xl border">
        {items.map((it) => (
          <details key={it.q} className="group px-4 py-3">
            <summary className="cursor-pointer list-none font-medium marker:hidden focus-visible:underline">
              <span aria-hidden className="mr-2 inline-block transition group-open:rotate-90">›</span>
              {it.q}
            </summary>
            <p className="mt-2 pl-5 text-muted-foreground">{it.a}</p>
          </details>
        ))}
      </div>
    </div>
  );
}
