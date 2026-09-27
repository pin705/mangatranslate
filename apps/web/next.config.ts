import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Rewrites are resolved at build time: set API_URL when running `next build` (see Dockerfile).
const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default createNextIntlPlugin()(nextConfig);
