import { NextResponse, type NextRequest } from "next/server";

// Cheap presence check only; the API enforces real authentication and authorization.
export function proxy(req: NextRequest) {
  const path = req.nextUrl.pathname + req.nextUrl.search;
  if (!req.cookies.has("mt_session")) {
    const url = new URL("/login", req.url);
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }
  const headers = new Headers(req.headers);
  headers.set("x-pathname", path);
  const res = NextResponse.next({ request: { headers } });
  res.headers.set("X-Robots-Tag", "noindex, nofollow");
  return res;
}

export const config = {
  matcher: ["/dashboard/:path*", "/jobs/:path*", "/billing/:path*", "/usage/:path*", "/settings/:path*", "/admin/:path*"],
};
