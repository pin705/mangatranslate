import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { JobView } from "@/components/job-view";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("job"))("title") };
}

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = await getTranslations("job");
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6">
      <Link href="/jobs" className="mb-4 inline-block text-sm text-muted-foreground hover:text-foreground">
        ← {t("back")}
      </Link>
      <JobView id={id} />
    </div>
  );
}
