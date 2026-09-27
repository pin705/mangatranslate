import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PaymentReturn } from "@/components/billing";
import { Page } from "@/components/page";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("billingReturn"))("title") };
}

export default async function BillingReturnPage({ searchParams }: { searchParams: Promise<{ payment_id?: string }> }) {
  const { payment_id } = await searchParams;
  const t = await getTranslations("billingReturn");
  return (
    <Page title={t("title")}>
      <PaymentReturn paymentId={typeof payment_id === "string" ? payment_id : undefined} />
    </Page>
  );
}
