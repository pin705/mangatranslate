import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AdminSystem } from "@/components/admin/config";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("admin.nav"))("system") };
}

export default function Page() {
  return <AdminSystem />;
}
