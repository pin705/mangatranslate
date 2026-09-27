"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Field, FormError } from "@/components/field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useUser } from "@/components/user-context";
import { api, type Locale, type User } from "@/lib/api";
import { setLocaleCookie } from "@/lib/utils";

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{title}</h2>
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function SettingsView() {
  const t = useTranslations("settings");
  const tn = useTranslations("nav");
  const router = useRouter();
  const { user, setUser } = useUser();

  const [locale, setLocale] = useState<Locale>(user.locale);
  const [langState, setLangState] = useState<{ busy: boolean; error: unknown; saved: boolean }>({ busy: false, error: null, saved: false });

  const [pw, setPw] = useState<{ busy: boolean; error: unknown; saved: boolean }>({ busy: false, error: null, saved: false });
  const [deletePassword, setDeletePassword] = useState("");

  async function saveLanguage() {
    setLangState({ busy: true, error: null, saved: false });
    try {
      setUser(await api<User>("/me", { method: "PATCH", json: { locale } }));
      setLocaleCookie(locale);
      setLangState({ busy: false, error: null, saved: true });
      router.refresh();
    } catch (error) {
      setLangState({ busy: false, error, saved: false });
    }
  }

  async function changePassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    if (f.get("new_password") !== f.get("confirm")) return setPw({ busy: false, error: t("password.mismatch"), saved: false });
    setPw({ busy: true, error: null, saved: false });
    try {
      await api("/me/password", {
        method: "POST",
        json: { current_password: f.get("current_password"), new_password: f.get("new_password") },
      });
      form.reset();
      setPw({ busy: false, error: null, saved: true });
    } catch (error) {
      setPw({ busy: false, error, saved: false });
    }
  }

  return (
    <div className="grid max-w-2xl gap-6">
      <Section title={t("language.title")} description={t("language.description")}>
        <div className="grid gap-4">
          <RadioGroup value={locale} onValueChange={(v) => setLocale(v as Locale)} aria-label={t("language.title")} className="grid gap-2">
            {(["vi", "en"] as const).map((l) => (
              <Label key={l} className="flex items-center gap-2 font-normal">
                <RadioGroupItem value={l} />
                {tn(`languageNames.${l}`)}
              </Label>
            ))}
          </RadioGroup>
          <FormError error={langState.error} />
          <div className="flex items-center gap-3">
            <Button onClick={saveLanguage} disabled={langState.busy || locale === user.locale}>
              {langState.busy && <Loader2 className="animate-spin" aria-hidden />}
              {t("save")}
            </Button>
            <span role="status" className="text-sm text-muted-foreground">
              {langState.saved ? t("saved") : ""}
            </span>
          </div>
        </div>
      </Section>

      <Section title={t("password.title")} description={t("password.description")}>
        <form onSubmit={changePassword} className="grid gap-4">
          <Field label={t("password.current")} name="current_password" type="password" autoComplete="current-password" required />
          <Field
            label={t("password.new")}
            name="new_password"
            type="password"
            autoComplete="new-password"
            minLength={10}
            maxLength={128}
            required
            hint={t("password.hint")}
          />
          <Field label={t("password.confirm")} name="confirm" type="password" autoComplete="new-password" required />
          <FormError error={pw.error} />
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={pw.busy}>
              {pw.busy && <Loader2 className="animate-spin" aria-hidden />}
              {t("password.submit")}
            </Button>
            <span role="status" className="text-sm text-muted-foreground">
              {pw.saved ? t("password.saved") : ""}
            </span>
          </div>
        </form>
      </Section>

      <Section title={t("delete.title")} description={t("delete.description")}>
        <ConfirmDialog
          trigger={<Button variant="destructive">{t("delete.button")}</Button>}
          title={t("delete.confirmTitle")}
          description={t("delete.confirmBody")}
          confirmLabel={t("delete.confirm")}
          destructive
          canConfirm={deletePassword.length > 0}
          onOpenChange={(o) => !o && setDeletePassword("")}
          onConfirm={async () => {
            await api("/me", { method: "DELETE", json: { password: deletePassword } });
            router.replace("/");
          }}
        >
          <Field
            label={t("delete.password")}
            type="password"
            autoComplete="current-password"
            value={deletePassword}
            onChange={(e) => setDeletePassword(e.target.value)}
            required
          />
        </ConfirmDialog>
      </Section>
    </div>
  );
}
