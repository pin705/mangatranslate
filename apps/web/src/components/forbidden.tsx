import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Button } from "@/components/ui/button";

export async function Forbidden() {
  const t = await getTranslations("forbidden");
  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center gap-3 px-4 py-16 text-center">
      <ShieldAlert className="size-10 text-destructive" aria-hidden />
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <p className="text-muted-foreground">{t("body")}</p>
      <Button asChild>
        <Link href="/dashboard">{t("back")}</Link>
      </Button>
    </div>
  );
}
