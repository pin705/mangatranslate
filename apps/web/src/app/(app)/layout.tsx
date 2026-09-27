import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { AppShell } from "@/components/app-shell";
import { Logo } from "@/components/logo";
import { ErrorState } from "@/components/states";
import { UserProvider } from "@/components/user-context";
import { describeError, type User } from "@/lib/api";
import { NO_INDEX } from "@/lib/seo";
import { getMe } from "@/lib/server-api";

export const metadata = NO_INDEX;

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  let user: User | null;
  try {
    user = await getMe();
  } catch (e) {
    const t = await getTranslations("errors");
    return (
      <main id="main" className="mx-auto w-full max-w-3xl px-4 py-10">
        <Logo />
        <ErrorState message={describeError(e, t)} />
      </main>
    );
  }
  if (!user) {
    const path = (await headers()).get("x-pathname") ?? "/dashboard";
    redirect(`/login?next=${encodeURIComponent(path)}`);
  }
  return (
    <UserProvider initial={user}>
      <AppShell>{children}</AppShell>
    </UserProvider>
  );
}
