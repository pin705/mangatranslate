import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AdminOverview } from "@/components/admin/overview";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("admin.nav"))("overview") };
}

export default function Page() {
  return <AdminOverview />;
}
