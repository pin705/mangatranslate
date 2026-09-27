import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { AdminNav } from "@/components/admin/nav";
import { Forbidden } from "@/components/forbidden";
import { isAdmin, type User } from "@/lib/api";
import { getMe } from "@/lib/server-api";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin");
  return { title: { template: `%s · ${t("title")}`, default: t("title") } };
}

// UI gate only — every /admin/* API call is authorised by the API itself.
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  let user: User | null;
  try {
    user = await getMe();
  } catch {
    return null; // the parent layout renders the error state
  }
  if (!user) redirect("/login?next=/admin");
  if (!isAdmin(user)) return <Forbidden />;
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col lg:flex-row">
      <AdminNav />
      <div className="min-w-0 flex-1 px-4 py-6">{children}</div>
    </div>
  );
}
