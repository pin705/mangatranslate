import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Page } from "@/components/page";
import { SettingsView } from "@/components/settings-view";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("settings"))("title") };
}

export default async function SettingsPage() {
  const t = await getTranslations("settings");
  return (
    <Page title={t("title")}>
      <SettingsView />
    </Page>
  );
}
