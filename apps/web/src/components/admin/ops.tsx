"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { AdminHeading, StatusFilter, useFmt } from "@/components/admin/common";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Pager } from "@/components/pager";
import { JobStatusBadge, PaymentStatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/hooks/use-api";
import {
  api,
  isTerminal,
  JOB_STATUSES,
  qs,
  type AdminJob,
  type AdminPayment,
  type AuditEntry,
  type JobStatus,
  type List,
  type PaymentStatus,
} from "@/lib/api";

const LIMIT = 20;
const PAYMENT_STATUSES: readonly PaymentStatus[] = ["pending", "paid", "cancelled", "failed", "refunded"];

export function AdminJobs() {
  const t = useTranslations("admin.jobs");
  const ts = useTranslations("jobStatus");
  const f = useFmt();
  const [status, setStatus] = useState<JobStatus | "">("");
  const [offset, setOffset] = useState(0);
  const res = useApi<List<AdminJob>>(`/admin/jobs${qs({ status, limit: LIMIT, offset })}`);

  return (
    <>
      <AdminHeading
        title={t("title")}
        actions={
          <StatusFilter
            value={status}
            options={JOB_STATUSES}
            label={t("filter")}
            optionLabel={(s) => ts(s)}
            onChange={(v) => {
              setStatus(v);
              setOffset(0);
            }}
          />
        }
      />
      {res.error ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : !res.data ? (
        <LoadingState rows={6} />
      ) : !res.data.total ? (
        <EmptyState>{t("empty")}</EmptyState>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("job")}</TableHead>
                <TableHead>{t("user")}</TableHead>
                <TableHead>{t("status")}</TableHead>
                <TableHead className="text-right">{t("pages")}</TableHead>
                <TableHead className="text-right">{t("credits")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("created")}</TableHead>
                <TableHead>
                  <span className="sr-only">{t("actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {res.data.items.map((j) => (
                <TableRow key={j.id}>
                  <TableCell className="max-w-48 truncate font-medium" title={j.id}>
                    {j.title || j.id.slice(0, 8)}
                  </TableCell>
                  <TableCell className="max-w-48 truncate">{j.user_email}</TableCell>
                  <TableCell>
                    <JobStatusBadge status={j.status} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {j.pages_done}/{j.page_count}
                    {j.pages_failed > 0 && <span className="text-destructive"> ({j.pages_failed}✕)</span>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {j.credits_charged}/{j.credits_reserved}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">{f.date(j.created_at)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      {(j.status === "PARTIAL" || j.status === "FAILED") && (
                        <ConfirmDialog
                          trigger={
                            <Button size="sm" variant="outline">
                              {t("retry")}
                            </Button>
                          }
                          title={t("retryTitle")}
                          description={t("retryBody", { email: j.user_email })}
                          confirmLabel={t("retry")}
                          onConfirm={async () => {
                            await api(`/admin/jobs/${j.id}/retry`, { method: "POST" });
                            res.reload();
                          }}
                        />
                      )}
                      {!isTerminal(j.status) && (
                        <ConfirmDialog
                          trigger={
                            <Button size="sm" variant="destructive">
                              {t("cancel")}
                            </Button>
                          }
                          title={t("cancelTitle")}
                          description={t("cancelBody", { email: j.user_email })}
                          confirmLabel={t("cancel")}
                          destructive
                          onConfirm={async () => {
                            await api(`/admin/jobs/${j.id}/cancel`, { method: "POST" });
                            res.reload();
                          }}
                        />
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager offset={offset} limit={LIMIT} total={res.data.total} onChange={setOffset} />
        </>
      )}
    </>
  );
}

function RefundDialog({ p, onDone }: { p: AdminPayment; onDone: () => void }) {
  const t = useTranslations("admin.payments");
  const f = useFmt();
  const [reason, setReason] = useState("");
  const [revoke, setRevoke] = useState(true);
  const ids = { reason: useId(), revoke: useId() };
  return (
    <ConfirmDialog
      trigger={
        <Button size="sm" variant="destructive">
          {t("refund")}
        </Button>
      }
      title={t("refundTitle")}
      description={t("refundBody", { amount: f.money(p.amount, p.currency), email: p.user_email })}
      confirmLabel={t("refund")}
      destructive
      canConfirm={reason.trim().length > 0}
      onOpenChange={(o) => {
        if (!o) {
          setReason("");
          setRevoke(true);
        }
      }}
      onConfirm={async () => {
        await api(`/admin/payments/${p.id}/refund`, { method: "POST", json: { reason: reason.trim(), revoke_credits: revoke } });
        onDone();
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor={ids.reason}>{t("reason")}</Label>
        <Textarea id={ids.reason} value={reason} onChange={(e) => setReason(e.target.value)} required />
      </div>
      <div className="flex items-center gap-2">
        <Checkbox id={ids.revoke} checked={revoke} onCheckedChange={(c) => setRevoke(c === true)} />
        <Label htmlFor={ids.revoke} className="font-normal">
          {t("revoke", { count: p.credits })}
        </Label>
      </div>
    </ConfirmDialog>
  );
}

export function AdminPayments() {
  const t = useTranslations("admin.payments");
  const tp = useTranslations("paymentStatus");
  const f = useFmt();
  const [status, setStatus] = useState<PaymentStatus | "">("");
  const [offset, setOffset] = useState(0);
  const res = useApi<List<AdminPayment>>(`/admin/payments${qs({ status, limit: LIMIT, offset })}`);

  return (
    <>
      <AdminHeading
        title={t("title")}
        actions={
          <StatusFilter
            value={status}
            options={PAYMENT_STATUSES}
            label={t("filter")}
            optionLabel={(s) => tp(s)}
            onChange={(v) => {
              setStatus(v);
              setOffset(0);
            }}
          />
        }
      />
      {res.error ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : !res.data ? (
        <LoadingState rows={6} />
      ) : !res.data.total ? (
        <EmptyState>{t("empty")}</EmptyState>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("date")}</TableHead>
                <TableHead>{t("user")}</TableHead>
                <TableHead>{t("product")}</TableHead>
                <TableHead className="text-right">{t("amount")}</TableHead>
                <TableHead className="text-right">{t("credits")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("provider")}</TableHead>
                <TableHead>{t("status")}</TableHead>
                <TableHead>
                  <span className="sr-only">{t("actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {res.data.items.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="text-muted-foreground">{f.date(p.created_at)}</TableCell>
                  <TableCell className="max-w-48 truncate">{p.user_email}</TableCell>
                  <TableCell>{p.product_code}</TableCell>
                  <TableCell className="text-right tabular-nums">{f.money(p.amount, p.currency)}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.credits}</TableCell>
                  <TableCell className="hidden md:table-cell">{p.provider}</TableCell>
                  <TableCell>
                    <PaymentStatusBadge status={p.status} />
                  </TableCell>
                  <TableCell className="text-right">{p.status === "paid" && <RefundDialog p={p} onDone={res.reload} />}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager offset={offset} limit={LIMIT} total={res.data.total} onChange={setOffset} />
        </>
      )}
    </>
  );
}

export function AdminAudit() {
  const t = useTranslations("admin.audit");
  const f = useFmt();
  const [offset, setOffset] = useState(0);
  const res = useApi<List<AuditEntry>>(`/admin/audit${qs({ limit: LIMIT, offset })}`);
  return (
    <>
      <AdminHeading title={t("title")} />
      {res.error ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : !res.data ? (
        <LoadingState rows={6} />
      ) : !res.data.total ? (
        <EmptyState>{t("empty")}</EmptyState>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("date")}</TableHead>
                <TableHead>{t("actor")}</TableHead>
                <TableHead>{t("action")}</TableHead>
                <TableHead>{t("target")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("details")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("ip")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {res.data.items.map((a) => {
                const meta = a.metadata && Object.keys(a.metadata as object).length ? JSON.stringify(a.metadata) : "";
                return (
                  <TableRow key={a.id}>
                    <TableCell className="text-muted-foreground">{f.date(a.created_at)}</TableCell>
                    <TableCell className="max-w-48 truncate">{a.actor_email ?? "–"}</TableCell>
                    <TableCell>
                      <code className="text-xs">{a.action}</code>
                    </TableCell>
                    <TableCell className="max-w-48 truncate text-xs">
                      {a.target_type === "user" && a.target_id ? (
                        <Link href="/admin/users" className="hover:underline">
                          {a.target_type}:{a.target_id}
                        </Link>
                      ) : (
                        [a.target_type, a.target_id].filter(Boolean).join(":") || "–"
                      )}
                    </TableCell>
                    <TableCell className="hidden max-w-72 truncate lg:table-cell" title={meta}>
                      <code className="text-xs">{meta}</code>
                    </TableCell>
                    <TableCell className="hidden text-xs md:table-cell">{a.ip ?? "–"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <Pager offset={offset} limit={LIMIT} total={res.data.total} onChange={setOffset} />
        </>
      )}
    </>
  );
}
