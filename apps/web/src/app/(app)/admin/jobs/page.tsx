import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AdminJobs } from "@/components/admin/ops";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("admin.nav"))("jobs") };
}

export default function Page() {
  return <AdminJobs />;
}
