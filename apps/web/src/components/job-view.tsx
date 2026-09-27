"use client";

import { Download, Loader2, PencilLine, RotateCcw, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { JobStatusBadge, PageStatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useUser } from "@/components/user-context";
import { useApi, useInterval } from "@/hooks/use-api";
import { useErrorText } from "@/hooks/use-error-text";
import { useLangName } from "@/hooks/use-lang-name";
import { api, ApiError, isTerminal, type Job, type PageSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export const needsAttention = (p: PageSummary) => p.status === "failed" || (p.status === "ready" && p.needs_review);

export function JobView({ id }: { id: string }) {
  const t = useTranslations("job");
  const tr = useTranslations("reviewReasons");
  const format = useFormatter();
  const text = useErrorText();
  const langName = useLangName();
  const router = useRouter();
  const { refresh: refreshUser } = useUser();

  const job = useApi<Job>(`/jobs/${id}`);
  const pages = useApi<PageSummary[]>(`/jobs/${id}/pages`);
  const [filter, setFilter] = useState<"all" | "attention">("all");
  const [download, setDownload] = useState<{ format: "zip" | "cbz" } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const status = job.data?.status;
  const running = status !== undefined && !isTerminal(status);
  useInterval(() => {
    job.reload();
    pages.reload();
  }, running ? 3000 : null);

  // Balance changes when a job settles (reservation released / pages charged).
  useEffect(() => {
    if (status && isTerminal(status)) refreshUser();
  }, [status, refreshUser]);

  if (job.error) {
    if (job.error instanceof ApiError && job.error.status === 404) return <EmptyState>{t("notFound")}</EmptyState>;
    return <ErrorState error={job.error} onRetry={job.reload} />;
  }
  if (!job.data) return <LoadingState rows={6} />;
  const j = job.data;
  const list = pages.data ?? [];
  const counts = {
    completed: list.filter((p) => p.status === "ready" && !p.needs_review).length,
    review: list.filter((p) => p.status === "ready" && p.needs_review).length,
    failed: list.filter((p) => p.status === "failed").length,
  };
  const shown = filter === "all" ? list : list.filter(needsAttention);
  const pct = j.page_count ? Math.round((j.pages_done / j.page_count) * 100) : 0;
  const canDownload = (j.status === "COMPLETED" || j.status === "PARTIAL") && j.pages_done > 0;
  const canRetry = j.status === "PARTIAL" || j.status === "FAILED";

  async function act(fn: () => Promise<unknown>) {
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(typeof e === "string" ? e : text(e));
    }
  }

  async function startDownload(fmt: "zip" | "cbz") {
    setDownload({ format: fmt });
    await act(async () => {
      try {
        // 202 {status: "preparing"} until the archive is built; poll every 2 s (max ~5 min).
        for (let i = 0; i < 150; i++) {
          const r = await api<{ status: "ready" | "preparing"; url?: string }>(`/jobs/${id}/download?format=${fmt}`);
          if (r.status === "ready" && r.url) return window.location.assign(r.url);
          await sleep(2000);
        }
        throw t("downloadTimeout");
      } finally {
        setDownload(null);
      }
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{j.title || t("untitled")}</h1>
            <JobStatusBadge status={j.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("meta", {
              source: langName(j.source_lang),
              target: langName(j.target_lang),
              mode: t(`mode.${j.mode}`),
              date: format.dateTime(new Date(j.created_at), { dateStyle: "medium", timeStyle: "short" }),
            })}
          </p>
          {j.expires_at && (
            <p className="text-sm text-muted-foreground">
              {t("expires", { date: format.dateTime(new Date(j.expires_at), { dateStyle: "medium" }) })}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {list.some((p) => p.status === "ready") && (
            <Button asChild>
              <Link href={`/jobs/${id}/editor`}>
                <PencilLine aria-hidden />
                {t("openEditor")}
              </Link>
            </Button>
          )}
          {(["zip", "cbz"] as const).map((fmt) => (
            <Button key={fmt} variant="outline" disabled={!canDownload || download !== null} onClick={() => startDownload(fmt)}>
              {download?.format === fmt ? <Loader2 className="animate-spin" aria-hidden /> : <Download aria-hidden />}
              {t(fmt === "zip" ? "downloadZip" : "downloadCbz")}
            </Button>
          ))}
          {canRetry && (
            <Button
              variant="outline"
              onClick={() =>
                act(async () => {
                  job.setData(await api<Job>(`/jobs/${id}/retry`, { method: "POST" }));
                  pages.reload();
                })
              }
            >
              <RotateCcw aria-hidden />
              {t("retry")}
            </Button>
          )}
          {running && (
            <ConfirmDialog
              trigger={
                <Button variant="outline">
                  <XCircle aria-hidden />
                  {t("cancel")}
                </Button>
              }
              title={t("cancelTitle")}
              description={t("cancelBody")}
              confirmLabel={t("cancel")}
              destructive
              onConfirm={async () => job.setData(await api<Job>(`/jobs/${id}/cancel`, { method: "POST" }))}
            />
          )}
          <ConfirmDialog
            trigger={
              <Button variant="destructive">
                <Trash2 aria-hidden />
                {t("delete")}
              </Button>
            }
            title={t("deleteTitle")}
            description={t("deleteBody")}
            confirmLabel={t("delete")}
            destructive
            onConfirm={async () => {
              await api(`/jobs/${id}`, { method: "DELETE" });
              router.push("/jobs");
            }}
          />
        </div>
      </div>

      <div aria-live="polite" className="text-sm">
        {download && <p>{t("preparing")}</p>}
        {actionError && (
          <p role="alert" className="text-destructive">
            {actionError}
          </p>
        )}
      </div>

      {j.error && (
        <Alert variant="destructive">
          <AlertDescription>
            {j.error.code === "INSUFFICIENT_CREDITS" ? (
              <p>
                {t("insufficient")}{" "}
                <Link href="/billing" className="font-medium underline underline-offset-4">
                  {t("buyCredits")}
                </Link>
              </p>
            ) : (
              <p>{j.error.message || t("failed")}</p>
            )}
          </AlertDescription>
        </Alert>
      )}

      <section aria-labelledby="progress-h" className="rounded-xl border p-4">
        <h2 id="progress-h" className="sr-only">
          {t("progressTitle")}
        </h2>
        <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm" aria-live="polite">
          <span className="font-medium">{t("progress", { done: j.pages_done, total: j.page_count })}</span>
          <span className="text-muted-foreground">
            {t("credits", { reserved: j.credits_reserved, charged: j.credits_charged })}
          </span>
        </div>
        <Progress value={pct} className="mt-2" aria-label={t("progressTitle")} />
        <dl className="mt-4 grid grid-cols-3 gap-2 text-center text-sm">
          {(
            [
              ["completed", counts.completed, "text-emerald-700 dark:text-emerald-400"],
              ["needsReview", counts.review, "text-amber-700 dark:text-amber-300"],
              ["failedPages", counts.failed, "text-destructive"],
            ] as const
          ).map(([k, n, cls]) => (
            <div key={k} className="rounded-lg bg-muted/50 p-2">
              <dt className="text-muted-foreground">{t(k)}</dt>
              <dd className={cn("text-xl font-semibold tabular-nums", cls)}>{n}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="pages-h">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 id="pages-h" className="text-lg font-semibold">
            {t("pages")}
          </h2>
          <div role="group" aria-label={t("filter")} className="inline-flex rounded-lg border p-0.5">
            {(["all", "attention"] as const).map((f) => (
              <Button key={f} size="sm" variant={filter === f ? "secondary" : "ghost"} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {t(`filters.${f}`, { count: f === "all" ? list.length : counts.review + counts.failed })}
              </Button>
            ))}
          </div>
        </div>
        {pages.error ? (
          <ErrorState error={pages.error} onRetry={pages.reload} />
        ) : !pages.data ? (
          <LoadingState rows={2} />
        ) : shown.length === 0 ? (
          <EmptyState>{filter === "all" ? t("noPages") : t("noProblems")}</EmptyState>
        ) : (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {shown.map((p) => {
              const src = p.output_url ?? p.source_url;
              return (
                <li key={p.id} className="flex flex-col overflow-hidden rounded-xl border">
                  <Link
                    href={`/jobs/${id}/editor?page=${p.id}`}
                    className="block bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                    aria-label={t("editPage", { n: p.index + 1 })}
                  >
                    {src ? (
                      <img
                        src={src}
                        alt=""
                        loading="lazy"
                        width={p.width || undefined}
                        height={p.height || undefined}
                        className="aspect-[3/4] w-full object-cover object-top"
                      />
                    ) : (
                      <div className="aspect-[3/4]" />
                    )}
                  </Link>
                  <div className="flex flex-1 flex-col gap-1 p-2 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{t("page", { n: p.index + 1 })}</span>
                      <PageStatusBadge page={p} />
                    </div>
                    {p.status === "failed" && <p className="text-xs text-destructive">{t("pageError", { n: p.index + 1 })}</p>}
                    {p.status === "ready" && p.needs_review && p.review_reasons.length > 0 && (
                      <ul className="text-xs text-muted-foreground">
                        {p.review_reasons.map((r) => (
                          <li key={r}>{tr.has(r) ? tr(r) : r}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
