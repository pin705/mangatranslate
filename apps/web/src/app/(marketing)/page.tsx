import { Eraser, Languages, Layers, ScanText, Type } from "lucide-react";
import { cookies } from "next/headers";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Button } from "@/components/ui/button";
import { pageMetadata, SITE_NAME, SITE_URL } from "@/lib/seo";

export const generateMetadata = () => pageMetadata("home", "/");

const STEPS = [
  { key: "ocr", Icon: ScanText },
  { key: "translate", Icon: Languages },
  { key: "clean", Icon: Eraser },
  { key: "typeset", Icon: Type },
  { key: "batch", Icon: Layers },
] as const;

export default async function Home() {
  const t = await getTranslations("home");
  const loggedIn = (await cookies()).has("mt_session");
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: SITE_NAME,
    applicationCategory: "MultimediaApplication",
    operatingSystem: "Web",
    url: SITE_URL,
    description: t("heroSubtitle"),
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }}
      />
      <section className="mx-auto flex w-full max-w-6xl flex-col items-center gap-6 px-4 py-16 text-center sm:py-24">
        <h1 className="max-w-3xl text-4xl font-bold tracking-tight text-balance sm:text-5xl">{t("heroTitle")}</h1>
        <p className="max-w-2xl text-lg text-muted-foreground text-balance">{t("heroSubtitle")}</p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button asChild size="lg">
            <Link href={loggedIn ? "/dashboard" : "/register"}>{t("cta")}</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/pricing">{t("seePricing")}</Link>
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">{t("heroNote")}</p>
      </section>

      <section aria-labelledby="showcase" className="bg-muted/40 py-16">
        <div className="mx-auto w-full max-w-5xl px-4">
          <h2 id="showcase" className="text-center text-2xl font-semibold">
            {t("showcaseTitle")}
          </h2>
          <p className="mx-auto mt-2 max-w-2xl text-center text-muted-foreground">{t("showcaseBody")}</p>
          <div className="mt-8 grid gap-6 sm:grid-cols-2">
            {(["original", "clean"] as const).map((k) => (
              <figure key={k} className="overflow-hidden rounded-xl border bg-background">
                <img
                  src={`/showcase/${k}.jpg`}
                  alt={t(k === "original" ? "originalAlt" : "cleanAlt")}
                  width={900}
                  height={1245}
                  className="h-auto w-full"
                />
                <figcaption className="border-t px-4 py-2 text-sm font-medium">
                  {t(k === "original" ? "original" : "textRemoved")}
                </figcaption>
              </figure>
            ))}
          </div>
          <p className="mt-4 text-center text-xs text-muted-foreground">{t("credit")}</p>
        </div>
      </section>

      <section aria-labelledby="steps" className="mx-auto w-full max-w-6xl px-4 py-16">
        <h2 id="steps" className="text-center text-2xl font-semibold">
          {t("stepsTitle")}
        </h2>
        <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map(({ key, Icon }, i) => (
            <li key={key} className="rounded-xl border p-5">
              <Icon className="size-6 text-primary" aria-hidden />
              <h3 className="mt-3 font-semibold">
                {i + 1}. {t(`steps.${key}.title`)}
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">{t(`steps.${key}.body`)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="expect" className="mx-auto w-full max-w-3xl px-4 pb-16">
        <h2 id="expect" className="text-2xl font-semibold">
          {t("expectTitle")}
        </h2>
        <ul className="mt-4 list-disc space-y-2 pl-5 text-muted-foreground">
          {(t.raw("expect") as string[]).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <div className="mt-8">
          <Button asChild size="lg">
            <Link href={loggedIn ? "/dashboard" : "/register"}>{t("cta")}</Link>
          </Button>
        </div>
      </section>
    </>
  );
}
