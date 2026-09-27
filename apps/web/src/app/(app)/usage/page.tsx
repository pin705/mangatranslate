import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { TransactionsTable } from "@/components/billing";
import { Page } from "@/components/page";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("usage"))("title") };
}

export default async function UsagePage() {
  const t = await getTranslations("usage");
  return (
    <Page title={t("title")} description={t("description")}>
      <TransactionsTable />
    </Page>
  );
}
