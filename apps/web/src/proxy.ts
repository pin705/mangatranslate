import { NextResponse, type NextRequest } from "next/server";

const PROTECTED = ["/dashboard", "/jobs", "/billing", "/usage", "/settings", "/admin"];

// Browsers upload to and load images from object storage directly (signed URLs), so its origin must be allowed.
// Set CSP_STORAGE_ORIGIN to the bucket endpoint in production (e.g. https://<account>.r2.cloudflarestorage.com).
const storage = process.env.CSP_STORAGE_ORIGIN ?? "https:";

function csp(nonce: string): string {
  const dev = process.env.NODE_ENV === "development";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    // Radix/shadcn and the editor position elements with inline style attributes; styles cannot run code.
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' blob: data: ${storage}`,
    `connect-src 'self' ${storage}`,
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(process.env.NEXT_PUBLIC_SITE_URL?.startsWith("https://") ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
}

export function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  const isProtected = PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  // Cheap presence check only; the API enforces real authentication and authorization.
  if (isProtected && !req.cookies.has("mt_session")) {
    const url = new URL("/login", req.url);
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const policy = csp(nonce);
  const headers = new Headers(req.headers);
  headers.set("x-nonce", nonce);
  headers.set("x-pathname", pathname + search);
  headers.set("Content-Security-Policy", policy); // Next reads the nonce from here for its own scripts
  const res = NextResponse.next({ request: { headers } });
  res.headers.set("Content-Security-Policy", policy);
  if (isProtected) res.headers.set("X-Robots-Tag", "noindex, nofollow");
  return res;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico|showcase|robots.txt|sitemap.xml).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
