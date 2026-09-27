import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { ForgotPasswordForm } from "@/components/auth-forms";
import { NO_INDEX } from "@/lib/seo";

export async function generateMetadata(): Promise<Metadata> {
  return { ...NO_INDEX, title: (await getTranslations("auth.forgot"))("title") };
}

export default function Page() {
  return <ForgotPasswordForm />;
}
