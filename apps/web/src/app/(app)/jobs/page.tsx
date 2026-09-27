import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { JobsList } from "@/components/jobs-list";
import { Page } from "@/components/page";
import { Button } from "@/components/ui/button";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("jobs"))("title") };
}

export default async function JobsPage() {
  const t = await getTranslations("jobs");
  return (
    <Page
      title={t("title")}
      actions={
        <Button asChild>
          <Link href="/jobs/new">{t("new")}</Link>
        </Button>
      }
    >
      <JobsList />
    </Page>
  );
}
