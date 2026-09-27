import { ProsePage } from "@/components/prose-page";
import { pageMetadata } from "@/lib/seo";

export const generateMetadata = () => pageMetadata("terms", "/terms");

export default function Page() {
  return <ProsePage ns="legal.terms" draft />;
}
