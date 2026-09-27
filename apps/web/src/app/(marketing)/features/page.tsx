import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { ProsePage } from "@/components/prose-page";
import { Button } from "@/components/ui/button";
import { pageMetadata } from "@/lib/seo";

export const generateMetadata = () => pageMetadata("features", "/features");

export default async function FeaturesPage() {
  const t = await getTranslations("features");
  return (
    <>
      <ProsePage ns="features" />
      <div className="mx-auto w-full max-w-3xl px-4 pb-16">
        <Button asChild size="lg">
          <Link href="/register">{t("cta")}</Link>
        </Button>
      </div>
    </>
  );
}
