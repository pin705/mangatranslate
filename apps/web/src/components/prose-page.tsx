import { FileWarning } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { Alert, AlertDescription } from "@/components/ui/alert";

type Section = { h: string; p: string[] };

/** Legal / info page from a messages namespace with `title`, `intro` and `sections: {h, p[]}[]`. */
export async function ProsePage({ ns, draft = false }: { ns: "legal.terms" | "legal.privacy" | "legal.copyright" | "features"; draft?: boolean }) {
  const t = await getTranslations(ns);
  const tl = await getTranslations("legal");
  return (
    <article className="mx-auto w-full max-w-3xl px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
      {draft && (
        <Alert className="mt-4 border-amber-500/50">
          <FileWarning aria-hidden />
          <AlertDescription className="font-medium">{tl("draft")}</AlertDescription>
        </Alert>
      )}
      <p className="mt-4 text-muted-foreground">{t("intro")}</p>
      {(t.raw("sections") as Section[]).map((s) => (
        <section key={s.h} className="mt-8">
          <h2 className="text-xl font-semibold">{s.h}</h2>
          {s.p.map((para) => (
            <p key={para} className="mt-2 leading-relaxed">
              {para}
            </p>
          ))}
        </section>
      ))}
    </article>
  );
}
