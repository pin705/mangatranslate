"use client";

import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Pager } from "@/components/pager";
import { PaymentStatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useUser } from "@/components/user-context";
import { useApi, useInterval } from "@/hooks/use-api";
import { useErrorText } from "@/hooks/use-error-text";
import { api, type CreditTransaction, type List, type Payment, type Product } from "@/lib/api";
import { cn } from "@/lib/utils";

const LIMIT = 20;

export function useMoney() {
  const format = useFormatter();
  return (amount: number, currency: string) => format.number(amount, { style: "currency", currency, maximumFractionDigits: currency === "VND" ? 0 : 2 });
}

export function BillingView() {
  const t = useTranslations("billing");
  const text = useErrorText();
  const money = useMoney();
  const balance = useApi<{ balance: number }>("/credits");
  const products = useApi<Product[]>("/products");
  const [buying, setBuying] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function buy(code: string) {
    setBuying(code);
    setError(null);
    try {
      const r = await api<{ payment_id: string; checkout_url: string }>("/billing/checkout", {
        method: "POST",
        json: { product_code: code },
      });
      window.location.assign(r.checkout_url);
    } catch (e) {
      setError(text(e));
      setBuying(null);
    }
  }

  return (
    <div className="space-y-10">
      <section aria-labelledby="balance-h" className="rounded-xl border p-5">
        <h2 id="balance-h" className="text-sm font-medium text-muted-foreground">
          {t("balance")}
        </h2>
        {balance.error ? (
          <ErrorState error={balance.error} onRetry={balance.reload} />
        ) : (
          <p className="mt-1 text-4xl font-bold tabular-nums">{balance.data ? t("credits", { count: balance.data.balance }) : "…"}</p>
        )}
      </section>

      <section aria-labelledby="buy-h">
        <h2 id="buy-h" className="text-lg font-semibold">
          {t("buyTitle")}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("buyNote")}</p>
        {error && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        )}
        {products.error ? (
          <ErrorState error={products.error} onRetry={products.reload} />
        ) : !products.data ? (
          <LoadingState rows={2} />
        ) : products.data.length === 0 ? (
          <EmptyState>{t("noProducts")}</EmptyState>
        ) : (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {products.data.map((p) => (
              <Card key={p.code}>
                <CardHeader>
                  <CardTitle>{p.name}</CardTitle>
                  <CardDescription>{t("credits", { count: p.credits })}</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{money(p.price_amount, p.currency)}</p>
                </CardContent>
                <CardFooter className="mt-auto">
                  <Button className="w-full" disabled={buying !== null} onClick={() => buy(p.code)}>
                    {buying === p.code && <Loader2 className="animate-spin" aria-hidden />}
                    {t("buy")}
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="payments-h">
        <h2 id="payments-h" className="mb-3 text-lg font-semibold">
          {t("payments")}
        </h2>
        <PaymentsTable />
      </section>

      <section aria-labelledby="tx-h">
        <h2 id="tx-h" className="mb-3 text-lg font-semibold">
          {t("transactions")}
        </h2>
        <TransactionsTable />
      </section>
    </div>
  );
}

function PaymentsTable() {
  const t = useTranslations("billing");
  const format = useFormatter();
  const money = useMoney();
  const [offset, setOffset] = useState(0);
  const res = useApi<List<Payment>>(`/billing/payments?limit=${LIMIT}&offset=${offset}`);
  if (res.error) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <LoadingState />;
  if (!res.data.total) return <EmptyState>{t("noPayments")}</EmptyState>;
  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("col.date")}</TableHead>
            <TableHead>{t("col.product")}</TableHead>
            <TableHead className="text-right">{t("col.credits")}</TableHead>
            <TableHead className="text-right">{t("col.amount")}</TableHead>
            <TableHead>{t("col.status")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {res.data.items.map((p) => (
            <TableRow key={p.id}>
              <TableCell>{format.dateTime(new Date(p.created_at), { dateStyle: "medium", timeStyle: "short" })}</TableCell>
              <TableCell>{p.product_code}</TableCell>
              <TableCell className="text-right tabular-nums">{p.credits}</TableCell>
              <TableCell className="text-right tabular-nums">{money(p.amount, p.currency)}</TableCell>
              <TableCell>
                <PaymentStatusBadge status={p.status} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Pager offset={offset} limit={LIMIT} total={res.data.total} onChange={setOffset} />
    </>
  );
}

/** Credit ledger (also the usage page). */
export function TransactionsTable() {
  const t = useTranslations("billing");
  const tk = useTranslations("creditKind");
  const format = useFormatter();
  const [offset, setOffset] = useState(0);
  const res = useApi<List<CreditTransaction>>(`/credits/transactions?limit=${LIMIT}&offset=${offset}`);
  if (res.error) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <LoadingState />;
  if (!res.data.total) return <EmptyState>{t("noTransactions")}</EmptyState>;
  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("col.date")}</TableHead>
            <TableHead>{t("col.kind")}</TableHead>
            <TableHead className="text-right">{t("col.amount")}</TableHead>
            <TableHead>{t("col.details")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {res.data.items.map((x) => (
            <TableRow key={x.id}>
              <TableCell>{format.dateTime(new Date(x.created_at), { dateStyle: "medium", timeStyle: "short" })}</TableCell>
              <TableCell>{tk.has(x.kind) ? tk(x.kind) : x.kind}</TableCell>
              <TableCell className={cn("text-right tabular-nums", x.amount > 0 ? "text-emerald-700 dark:text-emerald-400" : "")}>
                {x.amount > 0 ? `+${x.amount}` : x.amount}
              </TableCell>
              <TableCell className="max-w-72 truncate text-muted-foreground">
                {x.job_id ? (
                  <Link href={`/jobs/${x.job_id}`} className="underline-offset-4 hover:underline">
                    {x.reason || t("viewJob")}
                  </Link>
                ) : (
                  x.reason
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Pager offset={offset} limit={LIMIT} total={res.data.total} onChange={setOffset} />
    </>
  );
}

const MAX_POLLS = 60; // 2 s × 60 ≈ 2 minutes

export function PaymentReturn({ paymentId }: { paymentId?: string }) {
  const t = useTranslations("billingReturn");
  const money = useMoney();
  const { refresh } = useUser();
  const res = useApi<Payment>(paymentId ? `/billing/payments/${paymentId}` : null);
  const [polls, setPolls] = useState(0);
  const status = res.data?.status;
  const polling = status === "pending" && polls < MAX_POLLS;
  useInterval(() => {
    setPolls((n) => n + 1);
    res.reload();
  }, polling ? 2000 : null);
  useEffect(() => {
    if (status === "paid") refresh();
  }, [status, refresh]);

  if (!paymentId) return <EmptyState>{t("missing")}</EmptyState>;
  if (res.error && !res.data) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <LoadingState />;
  const p = res.data;
  const [Icon, cls] =
    p.status === "paid" ? [CheckCircle2, "text-emerald-600"] : p.status === "pending" ? [Clock, "text-sky-600"] : [XCircle, "text-destructive"];

  return (
    <div className="max-w-xl space-y-4 rounded-xl border p-6">
      <div className="flex items-center gap-3" role="status" aria-live="polite">
        <Icon className={cn("size-8 shrink-0", cls)} aria-hidden />
        <div>
          <p className="text-lg font-semibold">{t(`status.${p.status}`)}</p>
          <p className="text-sm text-muted-foreground">
            {p.product_code} · {t("credits", { count: p.credits })} · {money(p.amount, p.currency)}
          </p>
        </div>
      </div>
      <p className="text-sm">{t("explain")}</p>
      {p.status === "pending" && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          {polling ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
          {polling ? t("checking") : t("timeout")}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {p.status === "pending" && !polling && (
          <Button variant="outline" onClick={() => (setPolls(0), res.reload())}>
            {t("checkAgain")}
          </Button>
        )}
        <Button asChild>
          <Link href="/billing">{t("back")}</Link>
        </Button>
        {p.status === "paid" && (
          <Button asChild variant="outline">
            <Link href="/jobs/new">{t("startTranslating")}</Link>
          </Button>
        )}
      </div>
    </div>
  );
}
