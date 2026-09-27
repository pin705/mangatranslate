import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AdminUsers } from "@/components/admin/users";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("admin.nav"))("users") };
}

export default function Page() {
  return <AdminUsers />;
}
