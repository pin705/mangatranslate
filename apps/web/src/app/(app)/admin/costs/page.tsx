import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AdminCosts } from "@/components/admin/overview";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("admin.nav"))("costs") };
}

export default function Page() {
  return <AdminCosts />;
}
