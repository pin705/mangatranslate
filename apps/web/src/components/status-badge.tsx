"use client";

import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { isTerminal, type JobStatus, type PageSummary, type PaymentStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const tone = {
  ok: "bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
  warn: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  bad: "bg-destructive/10 text-destructive",
  muted: "bg-muted text-muted-foreground",
  busy: "bg-sky-600/10 text-sky-700 dark:text-sky-300",
};

const JOB_TONE: Partial<Record<JobStatus, keyof typeof tone>> = {
  COMPLETED: "ok",
  PARTIAL: "warn",
  FAILED: "bad",
  CANCELLED: "muted",
  EXPIRED: "muted",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const t = useTranslations("jobStatus");
  return (
    <Badge className={cn(tone[JOB_TONE[status] ?? "busy"])}>
      {!isTerminal(status) && <Loader2 className="animate-spin" aria-hidden />}
      {t(status)}
    </Badge>
  );
}

export function PageStatusBadge({ page }: { page: Pick<PageSummary, "status" | "needs_review"> }) {
  const t = useTranslations("pageStatus");
  if (page.status === "ready" && page.needs_review) return <Badge className={tone.warn}>{t("review")}</Badge>;
  const k = { ready: "ok", failed: "bad", pending: "muted", processing: "busy" } as const;
  return <Badge className={tone[k[page.status]]}>{t(page.status)}</Badge>;
}

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  const t = useTranslations("paymentStatus");
  const k = { paid: "ok", pending: "busy", cancelled: "muted", failed: "bad", refunded: "warn" } as const;
  return <Badge className={tone[k[status]]}>{t(status)}</Badge>;
}
