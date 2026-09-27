import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { VerifyEmailBanner } from "@/components/dashboard-view";
import { NewTranslation } from "@/components/new-translation";
import { Page } from "@/components/page";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("upload"))("title") };
}

export default async function NewJobPage() {
  const t = await getTranslations("upload");
  return (
    <Page title={t("title")}>
      <div className="max-w-3xl">
        <VerifyEmailBanner />
        <NewTranslation />
      </div>
    </Page>
  );
}
