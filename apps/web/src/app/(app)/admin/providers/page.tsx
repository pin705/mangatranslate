import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AdminProviders } from "@/components/admin/config";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("admin.nav"))("providers") };
}

export default function Page() {
  return <AdminProviders />;
}
