"use client";

import { MailWarning } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { JobsTable } from "@/components/jobs-table";
import { NewTranslation } from "@/components/new-translation";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useUser } from "@/components/user-context";
import { useApi, useInterval } from "@/hooks/use-api";
import { useErrorText } from "@/hooks/use-error-text";
import { api, isTerminal, type Job, type List } from "@/lib/api";

export function VerifyEmailBanner() {
  const t = useTranslations("dashboard.verify");
  const text = useErrorText();
  const { user } = useUser();
  const [state, setState] = useState<"idle" | "busy" | "sent" | string>("idle");
  if (user.email_verified) return null;
  async function resend() {
    setState("busy");
    try {
      await api("/auth/resend-verification", { method: "POST" });
      setState("sent");
    } catch (e) {
      setState(text(e));
    }
  }
  return (
    <Alert className="mb-6 border-amber-500/50">
      <MailWarning aria-hidden />
      <AlertTitle>{t("title")}</AlertTitle>
      <AlertDescription>
        <p>{t("body", { email: user.email })}</p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Button size="sm" variant="outline" onClick={resend} disabled={state === "busy" || state === "sent"}>
            {t("resend")}
          </Button>
          <span aria-live="polite" className="text-sm">
            {state === "sent" ? t("sent") : state !== "idle" && state !== "busy" ? state : ""}
          </span>
        </div>
      </AlertDescription>
    </Alert>
  );
}

/** Job list that re-polls every 5 s while any listed job is still running. */
export function useJobList(path: string) {
  const res = useApi<List<Job>>(path);
  const running = res.data?.items.some((j) => !isTerminal(j.status)) ?? false;
  useInterval(res.reload, running ? 5000 : null);
  return res;
}

export function DashboardView() {
  const t = useTranslations("dashboard");
  const { user } = useUser();
  const jobs = useJobList("/jobs?limit=5&offset=0");

  return (
    <>
      <VerifyEmailBanner />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2 className="text-base font-medium text-muted-foreground">{t("balance")}</h2>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-4xl font-bold tabular-nums">{t("credits", { count: user.credits })}</p>
              <Button asChild variant="outline" className="w-full">
                <Link href="/billing">{t("buy")}</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
        <div className="lg:col-span-2">
          <NewTranslation compact />
        </div>
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>
              <h2 className="text-lg font-semibold">{t("recent")}</h2>
            </CardTitle>
            <CardAction>
              <Link href="/jobs" className="text-sm underline-offset-4 hover:underline">
                {t("viewAll")}
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent>
            {jobs.error ? (
              <ErrorState error={jobs.error} onRetry={jobs.reload} />
            ) : !jobs.data ? (
              <LoadingState />
            ) : jobs.data.items.length === 0 ? (
              <EmptyState>{t("noJobs")}</EmptyState>
            ) : (
              <JobsTable jobs={jobs.data.items} />
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
