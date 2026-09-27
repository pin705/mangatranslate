import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { VerifyEmail } from "@/components/auth-forms";
import { NO_INDEX } from "@/lib/seo";

export async function generateMetadata(): Promise<Metadata> {
  return { ...NO_INDEX, title: (await getTranslations("auth.verify"))("title") };
}

export default async function Page({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return <VerifyEmail token={typeof token === "string" ? token : undefined} />;
}
