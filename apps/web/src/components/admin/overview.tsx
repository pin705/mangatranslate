"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { AdminHeading, useFmt } from "@/components/admin/common";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { JOB_STATUSES, type AdminMetrics, type CostRow } from "@/lib/api";

export function AdminOverview() {
  const t = useTranslations("admin.overview");
  const ts = useTranslations("jobStatus");
  const f = useFmt();
  const m = useApi<AdminMetrics>("/admin/metrics");

  return (
    <>
      <AdminHeading title={t("title")} />
      {m.error ? (
        <ErrorState error={m.error} onRetry={m.reload} />
      ) : !m.data ? (
        <LoadingState rows={4} />
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            {(
              [
                ["users", f.num(m.data.users)],
                ["activeUsers", f.num(m.data.active_users_30d)],
                ["pages", f.num(m.data.pages_processed)],
                ["revenue", Object.entries(m.data.revenue).map(([cur, v]) => f.money(v, cur)).join(" · ") || "0"],
                ["aiCost", f.usd(m.data.ai_cost_usd)],
                ["margin", f.usd(m.data.gross_margin_usd)],
                ["costPerPage", f.usd(m.data.avg_cost_per_page_usd, 4)],
                ["avgTime", t("seconds", { s: Math.round(m.data.avg_processing_seconds) })],
                ["failedJobs", f.num(m.data.failed_jobs_30d)],
              ] as const
            ).map(([k, v]) => (
              <div key={k} className="rounded-xl border p-4">
                <dt className="text-xs text-muted-foreground">{t(k)}</dt>
                <dd className="mt-1 text-xl font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          <section aria-labelledby="jbs" className="mt-6">
            <h2 id="jbs" className="mb-2 font-semibold">
              {t("jobsByStatus")}
            </h2>
            <ul className="flex flex-wrap gap-2 text-sm">
              {JOB_STATUSES.filter((s) => m.data?.jobs_by_status[s]).map((s) => (
                <li key={s} className="rounded-lg border px-3 py-1.5">
                  {ts(s)}: <span className="font-semibold tabular-nums">{m.data?.jobs_by_status[s]}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
      <section aria-labelledby="costs-h" className="mt-8">
        <h2 id="costs-h" className="mb-2 font-semibold">
          {t("costs30")}
        </h2>
        <CostsTable days={30} />
      </section>
    </>
  );
}

export function CostsTable({ days }: { days: number }) {
  const t = useTranslations("admin.costs");
  const f = useFmt();
  const res = useApi<CostRow[]>(`/admin/costs?days=${days}`);
  if (res.error) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <LoadingState />;
  if (!res.data.length) return <EmptyState>{t("empty")}</EmptyState>;
  const sum = res.data.reduce((a, r) => ({ pages: a.pages + r.pages, cost: a.cost + r.ai_cost_usd, rev: a.rev + r.revenue_vnd }), {
    pages: 0,
    cost: 0,
    rev: 0,
  });
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("date")}</TableHead>
          <TableHead className="text-right">{t("pages")}</TableHead>
          <TableHead className="text-right">{t("aiCost")}</TableHead>
          <TableHead className="text-right">{t("revenue")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {res.data.map((r) => (
          <TableRow key={r.date}>
            <TableCell>{f.day(r.date)}</TableCell>
            <TableCell className="text-right tabular-nums">{f.num(r.pages)}</TableCell>
            <TableCell className="text-right tabular-nums">{f.usd(r.ai_cost_usd)}</TableCell>
            <TableCell className="text-right tabular-nums">{f.money(r.revenue_vnd, "VND")}</TableCell>
          </TableRow>
        ))}
      </TableBody>
      <TableFooter>
        <TableRow>
          <TableCell className="font-medium">{t("total")}</TableCell>
          <TableCell className="text-right tabular-nums">{f.num(sum.pages)}</TableCell>
          <TableCell className="text-right tabular-nums">{f.usd(sum.cost)}</TableCell>
          <TableCell className="text-right tabular-nums">{f.money(sum.rev, "VND")}</TableCell>
        </TableRow>
      </TableFooter>
    </Table>
  );
}

export function AdminCosts() {
  const t = useTranslations("admin.costs");
  const [days, setDays] = useState(30);
  return (
    <>
      <AdminHeading
        title={t("title")}
        actions={
          <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
            <SelectTrigger aria-label={t("range")} className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[7, 30, 90].map((d) => (
                <SelectItem key={d} value={String(d)}>
                  {t("lastDays", { count: d })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />
      <CostsTable days={days} />
    </>
  );
}
