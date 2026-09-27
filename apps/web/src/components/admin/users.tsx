"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { AdminHeading, useFmt } from "@/components/admin/common";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Pager } from "@/components/pager";
import { JobStatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/hooks/use-api";
import { api, qs, type AdminUser, type CreditTransaction, type Job, type List } from "@/lib/api";

const LIMIT = 20;

function SearchBox({ onSearch, initial = "" }: { onSearch: (q: string) => void; initial?: string }) {
  const t = useTranslations("admin.users");
  const [q, setQ] = useState(initial);
  const id = useId();
  return (
    <form
      role="search"
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSearch(q.trim());
      }}
    >
      <Label htmlFor={id} className="sr-only">
        {t("search")}
      </Label>
      <Input id={id} type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchPlaceholder")} className="w-64" />
      <Button type="submit" variant="outline">
        <Search aria-hidden />
        {t("search")}
      </Button>
    </form>
  );
}

export function UserStatusBadge({ status }: { status: AdminUser["status"] }) {
  const t = useTranslations("userStatus");
  return <Badge variant={status === "active" ? "secondary" : "destructive"}>{t.has(status) ? t(status) : status}</Badge>;
}

export function AdminUsers() {
  const t = useTranslations("admin.users");
  const f = useFmt();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const res = useApi<List<AdminUser>>(`/admin/users${qs({ q, limit: LIMIT, offset })}`);

  return (
    <>
      <AdminHeading
        title={t("title")}
        actions={
          <SearchBox
            onSearch={(v) => {
              setQ(v);
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
                <TableHead>{t("email")}</TableHead>
                <TableHead>{t("role")}</TableHead>
                <TableHead>{t("status")}</TableHead>
                <TableHead className="text-right">{t("credits")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("created")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {res.data.items.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>
                    <button type="button" className="text-left font-medium hover:underline" onClick={() => setOpenId(u.id)}>
                      {u.email}
                    </button>
                    {!u.email_verified && <span className="ml-2 text-xs text-muted-foreground">{t("unverified")}</span>}
                  </TableCell>
                  <TableCell>{u.role}</TableCell>
                  <TableCell>
                    <UserStatusBadge status={u.status} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{u.credits}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{f.date(u.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager offset={offset} limit={LIMIT} total={res.data.total} onChange={setOffset} />
        </>
      )}
      <Sheet open={openId !== null} onOpenChange={(o) => !o && setOpenId(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {openId && <UserDetail id={openId} onChanged={res.reload} />}
        </SheetContent>
      </Sheet>
    </>
  );
}

function UserDetail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const t = useTranslations("admin.users");
  const tk = useTranslations("creditKind");
  const f = useFmt();
  const res = useApi<{ user: AdminUser; jobs: Job[]; transactions: CreditTransaction[] }>(`/admin/users/${id}`);
  const [reason, setReason] = useState("");
  const reasonId = useId();
  const changed = () => {
    res.reload();
    onChanged();
  };

  if (res.error) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <LoadingState rows={6} />;
  const { user, jobs, transactions } = res.data;
  const suspended = user.status === "suspended";

  return (
    <div className="grid gap-6 p-4">
      <SheetHeader className="p-0">
        <SheetTitle className="break-all">{user.email}</SheetTitle>
        <SheetDescription>
          {user.role} · {t("credits")}: {user.credits} · {f.date(user.created_at)}
        </SheetDescription>
        <div>
          <UserStatusBadge status={user.status} />
        </div>
      </SheetHeader>

      {user.status !== "deleted" && (
        <ConfirmDialog
          trigger={<Button variant={suspended ? "outline" : "destructive"}>{suspended ? t("restore") : t("suspend")}</Button>}
          title={suspended ? t("restoreTitle") : t("suspendTitle")}
          description={suspended ? t("restoreBody") : t("suspendBody")}
          confirmLabel={suspended ? t("restore") : t("suspend")}
          destructive={!suspended}
          canConfirm={reason.trim().length > 0}
          onOpenChange={(o) => !o && setReason("")}
          onConfirm={async () => {
            await api(`/admin/users/${id}/${suspended ? "restore" : "suspend"}`, { method: "POST", json: { reason: reason.trim() } });
            changed();
          }}
        >
          <div className="grid gap-1.5">
            <Label htmlFor={reasonId}>{t("reason")}</Label>
            <Textarea id={reasonId} value={reason} onChange={(e) => setReason(e.target.value)} required />
          </div>
        </ConfirmDialog>
      )}

      <section>
        <h3 className="mb-2 font-semibold">{t("adjustCredits")}</h3>
        <CreditAdjust userId={id} email={user.email} onDone={changed} />
      </section>

      <section>
        <h3 className="mb-2 font-semibold">{t("jobs")}</h3>
        {jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noJobs")}</p>
        ) : (
          <ul className="divide-y rounded-lg border text-sm">
            {jobs.map((j) => (
              <li key={j.id} className="flex items-center justify-between gap-2 px-3 py-2">
                <span className="min-w-0 truncate">{j.title || j.id}</span>
                <JobStatusBadge status={j.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-2 font-semibold">{t("transactions")}</h3>
        {transactions.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noTransactions")}</p>
        ) : (
          <Table>
            <TableBody>
              {transactions.map((x) => (
                <TableRow key={x.id}>
                  <TableCell className="text-muted-foreground">{f.date(x.created_at)}</TableCell>
                  <TableCell>{tk.has(x.kind) ? tk(x.kind) : x.kind}</TableCell>
                  <TableCell className="text-right tabular-nums">{x.amount > 0 ? `+${x.amount}` : x.amount}</TableCell>
                  <TableCell className="max-w-40 truncate text-muted-foreground">{x.reason}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}

/** Grant or revoke credits with a mandatory reason, behind a confirmation. */
export function CreditAdjust({ userId, email, onDone }: { userId: string; email: string; onDone: () => void }) {
  const t = useTranslations("admin.credits");
  const [dir, setDir] = useState<"grant" | "revoke">("grant");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const ids = { amount: useId(), reason: useId() };
  const n = Number.parseInt(amount, 10);
  const valid = Number.isInteger(n) && n > 0 && reason.trim().length > 0;

  return (
    <div className="grid gap-3 rounded-lg border p-3">
      <RadioGroup value={dir} onValueChange={(v) => setDir(v as "grant" | "revoke")} aria-label={t("direction")} className="flex gap-4">
        {(["grant", "revoke"] as const).map((d) => (
          <Label key={d} className="flex items-center gap-2 font-normal">
            <RadioGroupItem value={d} />
            {t(d)}
          </Label>
        ))}
      </RadioGroup>
      <div className="grid gap-1.5">
        <Label htmlFor={ids.amount}>{t("amount")}</Label>
        <Input id={ids.amount} type="number" min={1} step={1} inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-32" />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={ids.reason}>{t("reason")}</Label>
        <Textarea id={ids.reason} value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
      </div>
      <div className="flex items-center gap-3">
        <ConfirmDialog
          trigger={
            <Button disabled={!valid} variant={dir === "revoke" ? "destructive" : "default"}>
              {t("apply")}
            </Button>
          }
          title={t("confirmTitle")}
          description={t(dir === "grant" ? "confirmGrant" : "confirmRevoke", { count: n || 0, email })}
          confirmLabel={t("apply")}
          destructive={dir === "revoke"}
          onConfirm={async () => {
            await api(`/admin/users/${userId}/credits`, {
              method: "POST",
              json: { amount: dir === "grant" ? n : -n, reason: reason.trim() },
            });
            setAmount("");
            setReason("");
            setDone(t("done"));
            onDone();
          }}
        />
        <span role="status" className="text-sm text-muted-foreground">
          {done}
        </span>
      </div>
    </div>
  );
}

export function AdminCredits() {
  const t = useTranslations("admin.credits");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<AdminUser | null>(null);
  const res = useApi<List<AdminUser>>(q ? `/admin/users${qs({ q, limit: 10, offset: 0 })}` : null);

  return (
    <>
      <AdminHeading title={t("title")} />
      <div className="grid max-w-2xl gap-6">
        <SearchBox
          onSearch={(v) => {
            setQ(v);
            setPicked(null);
          }}
        />
        {q &&
          (res.error ? (
            <ErrorState error={res.error} onRetry={res.reload} />
          ) : !res.data ? (
            <LoadingState rows={2} />
          ) : res.data.items.length === 0 ? (
            <EmptyState>{t("noMatch")}</EmptyState>
          ) : (
            <ul className="divide-y rounded-lg border text-sm">
              {res.data.items.map((u) => (
                <li key={u.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <span className="min-w-0 truncate">
                    {u.email} <span className="text-muted-foreground">· {u.credits}</span>
                  </span>
                  <Button size="sm" variant={picked?.id === u.id ? "secondary" : "outline"} aria-pressed={picked?.id === u.id} onClick={() => setPicked(u)}>
                    {t("select")}
                  </Button>
                </li>
              ))}
            </ul>
          ))}
        {picked && (
          <section aria-label={picked.email}>
            <p className="mb-2 text-sm">
              {t("selected", { email: picked.email })}{" "}
              <Link href="/admin/users" className="underline underline-offset-4">
                {t("openUsers")}
              </Link>
            </p>
            <CreditAdjust userId={picked.id} email={picked.email} onDone={res.reload} />
          </section>
        )}
      </div>
    </>
  );
}
