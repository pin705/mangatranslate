import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { BillingView } from "@/components/billing";
import { Page } from "@/components/page";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("billing"))("title") };
}

export default async function BillingPage() {
  const t = await getTranslations("billing");
  return (
    <Page title={t("title")}>
      <BillingView />
    </Page>
  );
}
