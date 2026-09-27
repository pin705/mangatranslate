import { headers } from "next/headers";
import { cache } from "react";
import { ApiError, request, type User } from "./api";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/** Server-side call to the API, forwarding the incoming cookie. Reading headers() also keeps the route dynamic. */
export async function serverApi<T>(path: string): Promise<T> {
  const h = await headers();
  return request<T>(`${API_URL}/api/v1${path}`, {
    headers: { cookie: h.get("cookie") ?? "", accept: "application/json" },
    cache: "no-store",
  });
}

/** Current user or null when logged out. Throws on other failures (e.g. API unreachable). Deduped per request. */
export const getMe = cache(async (): Promise<User | null> => {
  try {
    return await serverApi<User>("/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
});
