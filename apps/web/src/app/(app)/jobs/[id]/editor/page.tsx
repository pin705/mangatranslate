import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { EditorLoader } from "@/components/editor/loader";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("editor"))("title") };
}

export default async function EditorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const [{ id }, { page }] = await Promise.all([params, searchParams]);
  return <EditorLoader jobId={id} pageId={typeof page === "string" ? page : undefined} />;
}
