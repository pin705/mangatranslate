import { ProsePage } from "@/components/prose-page";
import { pageMetadata } from "@/lib/seo";

export const generateMetadata = () => pageMetadata("copyright", "/copyright");

export default function Page() {
  return <ProsePage ns="legal.copyright" draft />;
}
