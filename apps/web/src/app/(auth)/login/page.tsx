import { LoginForm } from "@/components/auth-forms";
import { pageMetadata } from "@/lib/seo";

export const generateMetadata = () => pageMetadata("login", "/login");

export default async function Page({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return <LoginForm next={typeof next === "string" ? next : undefined} />;
}
