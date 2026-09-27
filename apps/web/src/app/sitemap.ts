import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/seo";

const PAGES = ["", "/features", "/pricing", "/faq", "/register", "/login", "/terms", "/privacy", "/copyright"];

export default function sitemap(): MetadataRoute.Sitemap {
  return PAGES.map((p) => ({ url: `${SITE_URL}${p}`, changeFrequency: "weekly", priority: p === "" ? 1 : 0.6 }));
}
