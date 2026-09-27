import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { DashboardView } from "@/components/dashboard-view";
import { Page } from "@/components/page";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("dashboard"))("title") };
}

export default async function DashboardPage() {
  const t = await getTranslations("dashboard");
  return (
    <Page title={t("title")}>
      <DashboardView />
    </Page>
  );
}
