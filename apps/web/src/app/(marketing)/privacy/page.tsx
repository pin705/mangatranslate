import { ProsePage } from "@/components/prose-page";
import { pageMetadata } from "@/lib/seo";

export const generateMetadata = () => pageMetadata("privacy", "/privacy");

export default function Page() {
  return <ProsePage ns="legal.privacy" draft />;
}
