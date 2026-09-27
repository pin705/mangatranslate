import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AdminAudit } from "@/components/admin/ops";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("admin.nav"))("audit") };
}

export default function Page() {
  return <AdminAudit />;
}
