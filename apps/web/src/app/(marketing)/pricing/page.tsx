import { Check } from "lucide-react";
import { cookies } from "next/headers";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { describeError, type Pricing, type Product } from "@/lib/api";
import { pageMetadata } from "@/lib/seo";
import { serverApi } from "@/lib/server-api";

export const generateMetadata = () => pageMetadata("pricing", "/pricing");

export default async function PricingPage() {
  const t = await getTranslations("pricing");
  const te = await getTranslations("errors");
  const format = await getFormatter();
  const loggedIn = (await cookies()).has("mt_session");

  let products: Product[];
  let pricing: Pricing;
  try {
    [products, pricing] = await Promise.all([serverApi<Product[]>("/products"), serverApi<Pricing>("/pricing")]);
  } catch (e) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-12">
        <h1 className="text-3xl font-bold">{t("title")}</h1>
        <ErrorState message={describeError(e, te)} />
      </div>
    );
  }

  const cpp = pricing.credits_per_page;
  const pages = (credits: number) => Math.floor(credits / Math.max(cpp.clean, 1));
  const buyHref = loggedIn ? "/billing" : "/register";

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-12">
      <header className="max-w-2xl">
        <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
        <p className="mt-2 text-muted-foreground">{t("subtitle")}</p>
      </header>

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>{t("free.title")}</CardTitle>
            <CardDescription>{t("free.desc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            <p className="text-3xl font-bold">{t("credits", { count: pricing.signup_bonus })}</p>
            <p className="text-sm text-muted-foreground">{t("approxPages", { count: pages(pricing.signup_bonus) })}</p>
          </CardContent>
          <CardFooter className="mt-auto">
            <Button asChild variant="outline" className="w-full">
              <Link href={loggedIn ? "/dashboard" : "/register"}>{t("free.cta")}</Link>
            </Button>
          </CardFooter>
        </Card>
        {products.map((p) => (
          <Card key={p.code}>
            <CardHeader>
              <CardTitle>{p.name}</CardTitle>
              <CardDescription>{t("credits", { count: p.credits })}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <p className="text-3xl font-bold">
                {format.number(p.price_amount, { style: "currency", currency: p.currency, maximumFractionDigits: 0 })}
              </p>
              <p className="text-sm text-muted-foreground">
                {t("perCredit", {
                  price: format.number(p.price_amount / Math.max(p.credits, 1), {
                    style: "currency",
                    currency: p.currency,
                    maximumFractionDigits: 0,
                  }),
                })}
              </p>
              <p className="text-sm text-muted-foreground">{t("approxPages", { count: pages(p.credits) })}</p>
            </CardContent>
            <CardFooter className="mt-auto">
              <Button asChild className="w-full">
                <Link href={buyHref}>{t("buy")}</Link>
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>
      {products.length === 0 && <p className="mt-4 text-sm text-muted-foreground">{t("noProducts")}</p>}

      <section aria-labelledby="details" className="mt-12 grid gap-8 md:grid-cols-2">
        <div>
          <h2 id="details" className="text-xl font-semibold">
            {t("details")}
          </h2>
          <dl className="mt-4 divide-y rounded-xl border text-sm">
            {[
              [t("perPageClean"), t("credits", { count: cpp.clean })],
              [t("perPageOverlay"), t("credits", { count: cpp.overlay })],
              [t("sourceLanguages"), pricing.languages.source.join(", ")],
              [t("targetLanguages"), pricing.languages.target.join(", ")],
              [t("maxPages"), format.number(pricing.limits.max_pages_per_job)],
              [t("maxUpload"), t("megabytes", { mb: pricing.limits.max_upload_mb })],
              [t("concurrentJobs"), format.number(pricing.limits.max_concurrent_jobs)],
              [t("retention"), t("days", { count: pricing.retention_days })],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 px-4 py-3">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="text-right font-medium">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <h2 className="text-xl font-semibold">{t("howCreditsWork")}</h2>
          <ul className="mt-4 space-y-3 text-sm">
            {(t.raw("notes") as string[]).map((n) => (
              <li key={n} className="flex gap-2">
                <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                <span>{n}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
