import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

export const LOCALES = ["vi", "en"] as const;
export type AppLocale = (typeof LOCALES)[number];

export default getRequestConfig(async () => {
  const locale: AppLocale = (await cookies()).get("NEXT_LOCALE")?.value === "en" ? "en" : "vi";
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
    // ponytail: one display time zone for everyone; switch to a per-user zone if the API ever stores one
    timeZone: "Asia/Ho_Chi_Minh",
  };
});
