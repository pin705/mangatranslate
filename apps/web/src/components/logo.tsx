import Link from "next/link";
import { SITE_NAME } from "@/lib/seo";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="font-semibold tracking-tight whitespace-nowrap">
      {SITE_NAME}
    </Link>
  );
}
