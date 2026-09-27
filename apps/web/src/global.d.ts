import type messages from "../messages/en.json";
import type { AppLocale } from "./i18n/request";

declare module "next-intl" {
  interface AppConfig {
    Locale: AppLocale;
    Messages: typeof messages;
  }
}
