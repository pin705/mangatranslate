"use client";

import { CheckCircle2, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Field, FormError } from "@/components/field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { api, type User } from "@/lib/api";
import { safeNext, setLocaleCookie } from "@/lib/utils";

function AuthCard({ title, description, children, footer }: { title: string; description?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1 className="text-xl font-semibold">{title}</h1>
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
      {footer && <CardFooter className="flex-col items-start gap-2 text-sm">{footer}</CardFooter>}
    </Card>
  );
}

function Submit({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <Button type="submit" className="w-full" disabled={busy}>
      {busy && <Loader2 className="animate-spin" aria-hidden />}
      {children}
    </Button>
  );
}

function Done({ children }: { children: ReactNode }) {
  return (
    <div role="status" className="flex gap-2 text-sm">
      <CheckCircle2 className="size-5 shrink-0 text-emerald-600" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

/** Shared submit state: runs fn with the form's values, captures the error. */
function useSubmit(fn: (f: FormData) => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await fn(new FormData(e.currentTarget));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, onSubmit };
}

const str = (f: FormData, k: string) => String(f.get(k) ?? "");

export function LoginForm({ next }: { next?: string }) {
  const t = useTranslations("auth");
  const router = useRouter();
  const { busy, error, onSubmit } = useSubmit(async (f) => {
    const user = await api<User>("/auth/login", { method: "POST", json: { email: str(f, "email"), password: str(f, "password") } });
    setLocaleCookie(user.locale);
    router.replace(safeNext(next));
    await new Promise(() => undefined); // keep the button busy until the next page replaces this one
  });
  return (
    <AuthCard
      title={t("login.title")}
      footer={
        <>
          <Link href="/forgot-password" className="underline underline-offset-4">
            {t("login.forgot")}
          </Link>
          <p>
            {t("login.noAccount")}{" "}
            <Link href="/register" className="underline underline-offset-4">
              {t("login.register")}
            </Link>
          </p>
        </>
      }
    >
      <form onSubmit={onSubmit} className="grid gap-4">
        <Field label={t("email")} name="email" type="email" autoComplete="email" required />
        <Field label={t("password")} name="password" type="password" autoComplete="current-password" required />
        <FormError error={error} />
        <Submit busy={busy}>{t("login.submit")}</Submit>
      </form>
    </AuthCard>
  );
}

export function RegisterForm() {
  const t = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const { busy, error, onSubmit } = useSubmit(async (f) => {
    await api<User>("/auth/register", {
      method: "POST",
      json: { email: str(f, "email"), password: str(f, "password"), locale },
    });
    router.replace("/dashboard");
    await new Promise(() => undefined);
  });
  return (
    <AuthCard
      title={t("register.title")}
      description={t("register.description")}
      footer={
        <p>
          {t("register.haveAccount")}{" "}
          <Link href="/login" className="underline underline-offset-4">
            {t("register.login")}
          </Link>
        </p>
      }
    >
      <form onSubmit={onSubmit} className="grid gap-4">
        <Field label={t("email")} name="email" type="email" autoComplete="email" required />
        <Field
          label={t("password")}
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={10}
          maxLength={128}
          required
          hint={t("passwordHint")}
        />
        <div className="flex items-start gap-2 text-sm">
          <Checkbox id="agree" name="agree" required className="mt-0.5" />
          <Label htmlFor="agree" className="block leading-snug font-normal">
            {t.rich("register.agree", {
              terms: (c) => (
                <Link href="/terms" className="underline underline-offset-4" target="_blank">
                  {c}
                </Link>
              ),
              privacy: (c) => (
                <Link href="/privacy" className="underline underline-offset-4" target="_blank">
                  {c}
                </Link>
              ),
            })}
          </Label>
        </div>
        <FormError error={error} />
        <Submit busy={busy}>{t("register.submit")}</Submit>
      </form>
    </AuthCard>
  );
}

export function VerifyEmail({ token }: { token?: string }) {
  const t = useTranslations("auth.verify");
  const [result, setResult] = useState<{ ok: true } | { error: unknown } | null>(null);
  const started = useRef(false);
  useEffect(() => {
    if (!token || started.current) return; // tokens are single-use: never post twice (StrictMode)
    started.current = true;
    api<User>("/auth/verify-email", { method: "POST", json: { token } }).then(
      () => setResult({ ok: true }),
      (error) => setResult({ error }),
    );
  }, [token]);

  return (
    <AuthCard title={t("title")}>
      <div aria-live="polite" className="grid gap-4">
        {!token ? (
          <FormError error={t("missing")} />
        ) : result === null ? (
          <p role="status" className="flex items-center gap-2 text-sm">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            {t("working")}
          </p>
        ) : "ok" in result ? (
          <Done>{t("done")}</Done>
        ) : (
          <FormError error={result.error} />
        )}
        {result !== null && (
          <Button asChild>
            <Link href="/dashboard">{t("continue")}</Link>
          </Button>
        )}
      </div>
    </AuthCard>
  );
}

export function ForgotPasswordForm() {
  const t = useTranslations("auth.forgot");
  const ta = useTranslations("auth");
  const [sent, setSent] = useState(false);
  const { busy, error, onSubmit } = useSubmit(async (f) => {
    await api("/auth/forgot-password", { method: "POST", json: { email: str(f, "email") } });
    setSent(true);
  });
  return (
    <AuthCard
      title={t("title")}
      description={t("description")}
      footer={
        <Link href="/login" className="underline underline-offset-4">
          {t("back")}
        </Link>
      }
    >
      {sent ? (
        <Done>{t("sent")}</Done>
      ) : (
        <form onSubmit={onSubmit} className="grid gap-4">
          <Field label={ta("email")} name="email" type="email" autoComplete="email" required />
          <FormError error={error} />
          <Submit busy={busy}>{t("submit")}</Submit>
        </form>
      )}
    </AuthCard>
  );
}

export function ResetPasswordForm({ token }: { token?: string }) {
  const t = useTranslations("auth.reset");
  const ta = useTranslations("auth");
  const [done, setDone] = useState(false);
  const { busy, error, onSubmit } = useSubmit(async (f) => {
    if (str(f, "password") !== str(f, "confirm")) throw ta("mismatch");
    await api("/auth/reset-password", { method: "POST", json: { token, password: str(f, "password") } });
    setDone(true);
  });
  return (
    <AuthCard title={t("title")}>
      {!token ? (
        <FormError error={t("missing")} />
      ) : done ? (
        <div className="grid gap-4">
          <Done>{t("done")}</Done>
          <Button asChild>
            <Link href="/login">{t("login")}</Link>
          </Button>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="grid gap-4">
          <Field
            label={t("password")}
            name="password"
            type="password"
            autoComplete="new-password"
            minLength={10}
            maxLength={128}
            required
            hint={ta("passwordHint")}
          />
          <Field label={t("confirm")} name="confirm" type="password" autoComplete="new-password" required />
          <FormError error={error} />
          <Submit busy={busy}>{t("submit")}</Submit>
        </form>
      )}
    </AuthCard>
  );
}
