import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AdminCredits } from "@/components/admin/users";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("admin.nav"))("credits") };
}

export default function Page() {
  return <AdminCredits />;
}
