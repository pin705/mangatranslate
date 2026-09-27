"use client";

import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { AdminHeading, asArray, useFmt } from "@/components/admin/common";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Field } from "@/components/field";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { api, type AdminProduct, type AiProvider, type AppSettings } from "@/lib/api";

/** Only the fields that differ from the original (PATCH bodies). */
function diff<T extends object>(orig: T, draft: T): Partial<T> {
  return Object.fromEntries(Object.entries(draft).filter(([k, v]) => orig[k as keyof T] !== v)) as Partial<T>;
}

// --- Providers ----------------------------------------------------------------------------------

export function AdminProviders() {
  const t = useTranslations("admin.providers");
  const res = useApi<AiProvider[]>("/admin/providers");
  return (
    <>
      <AdminHeading title={t("title")} />
      <p className="mb-4 text-sm text-muted-foreground">{t("note")}</p>
      {res.error ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : !res.data ? (
        <LoadingState rows={4} />
      ) : !res.data.length ? (
        <EmptyState>{t("empty")}</EmptyState>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {res.data.map((p) => (
            // Remount with fresh drafts whenever the server copy changes.
            <ProviderCard key={JSON.stringify(p)} p={p} onSaved={res.reload} />
          ))}
        </div>
      )}
    </>
  );
}

function ProviderCard({ p, onSaved }: { p: AiProvider; onSaved: () => void }) {
  const t = useTranslations("admin.providers");
  const orig = {
    enabled: p.enabled,
    priority: p.priority,
    model: p.model,
    input_price_per_1m: Number(p.input_price_per_1m),
    output_price_per_1m: Number(p.output_price_per_1m),
  };
  const [draft, setDraft] = useState(orig);
  const changes = diff(orig, draft);
  const dirty = Object.keys(changes).length > 0;
  const valid = draft.model.trim() && Number.isFinite(draft.priority) && draft.input_price_per_1m >= 0 && draft.output_price_per_1m >= 0;
  const enabledId = useId();
  const num = (v: string) => (v === "" ? Number.NaN : Number(v));

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <CardTitle>
          <h2 className="text-base font-semibold">
            {p.name} <span className="text-sm font-normal text-muted-foreground">({p.kind})</span>
          </h2>
          <p className="mt-1 text-xs font-normal break-all text-muted-foreground">{p.base_url}</p>
        </CardTitle>
        <Badge variant={p.healthy ? "secondary" : "destructive"}>{p.healthy ? t("healthy") : t("unhealthy")}</Badge>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex items-center justify-between">
          <Label htmlFor={enabledId}>{t("enabled")}</Label>
          <Switch id={enabledId} checked={draft.enabled} onCheckedChange={(v) => setDraft({ ...draft, enabled: v })} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("model")} value={draft.model} onChange={(e) => setDraft({ ...draft, model: e.target.value })} />
          <Field
            label={t("priority")}
            hint={t("priorityHint")}
            type="number"
            step={1}
            value={Number.isNaN(draft.priority) ? "" : draft.priority}
            onChange={(e) => setDraft({ ...draft, priority: num(e.target.value) })}
          />
          <Field
            label={t("inputPrice")}
            type="number"
            min={0}
            step="any"
            value={Number.isNaN(draft.input_price_per_1m) ? "" : draft.input_price_per_1m}
            onChange={(e) => setDraft({ ...draft, input_price_per_1m: num(e.target.value) })}
          />
          <Field
            label={t("outputPrice")}
            type="number"
            min={0}
            step="any"
            value={Number.isNaN(draft.output_price_per_1m) ? "" : draft.output_price_per_1m}
            onChange={(e) => setDraft({ ...draft, output_price_per_1m: num(e.target.value) })}
          />
        </div>
        <div className="flex gap-2">
          <ConfirmDialog
            trigger={<Button disabled={!dirty || !valid}>{t("save")}</Button>}
            title={t("confirmTitle", { name: p.name })}
            description={
              <span className="block">
                {Object.entries(changes).map(([k, v]) => (
                  <span key={k} className="block">
                    <code>{k}</code> → <code>{String(v)}</code>
                  </span>
                ))}
              </span>
            }
            confirmLabel={t("save")}
            destructive={changes.enabled === false}
            onConfirm={async () => {
              await api(`/admin/providers/${p.id}`, { method: "PATCH", json: changes });
              onSaved();
            }}
          />
          <Button variant="ghost" disabled={!dirty} onClick={() => setDraft(orig)}>
            {t("reset")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// --- System settings + products -----------------------------------------------------------------

const SETTING_KEYS = [
  "credits_per_page_clean",
  "credits_per_page_overlay",
  "signup_bonus",
  "usd_vnd_rate",
  "max_pages_per_job",
  "max_concurrent_jobs",
  "retention_days",
] as const satisfies readonly (keyof AppSettings)[];

export function AdminSystem() {
  const t = useTranslations("admin.system");
  return (
    <>
      <AdminHeading title={t("title")} />
      <div className="grid gap-8">
        <SettingsForm />
        <Products />
      </div>
    </>
  );
}

function SettingsForm() {
  const res = useApi<AppSettings>("/admin/settings");
  if (res.error) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <LoadingState rows={4} />;
  return <SettingsDraft key={JSON.stringify(res.data)} orig={res.data} onSaved={res.setData} />;
}

function SettingsDraft({ orig, onSaved }: { orig: AppSettings; onSaved: (s: AppSettings) => void }) {
  const t = useTranslations("admin.system");
  const [draft, setDraft] = useState<Record<keyof AppSettings, string>>(
    () => Object.fromEntries(SETTING_KEYS.map((k) => [k, String(orig[k] ?? "")])) as Record<keyof AppSettings, string>,
  );
  const parsed = Object.fromEntries(SETTING_KEYS.map((k) => [k, Number(draft[k])])) as unknown as AppSettings;
  const valid = SETTING_KEYS.every((k) => draft[k] !== "" && Number.isFinite(parsed[k]) && parsed[k] >= 0);
  const changes = diff(orig, parsed);
  const dirty = Object.keys(changes).length > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("settings")}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SETTING_KEYS.map((k) => (
            <Field
              key={k}
              label={t(`keys.${k}`)}
              type="number"
              min={0}
              step="any"
              value={draft[k]}
              onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
            />
          ))}
        </div>
        <div>
          <ConfirmDialog
            trigger={<Button disabled={!dirty || !valid}>{t("saveSettings")}</Button>}
            title={t("confirmSettings")}
            description={
              <span className="block">
                {Object.entries(changes).map(([k, v]) => (
                  <span key={k} className="block">
                    {t(`keys.${k as keyof AppSettings}`)}: <code>{String(orig[k as keyof AppSettings])}</code> → <code>{String(v)}</code>
                  </span>
                ))}
              </span>
            }
            confirmLabel={t("saveSettings")}
            onConfirm={async () => onSaved(await api<AppSettings>("/admin/settings", { method: "PATCH", json: changes }))}
          />
        </div>
      </CardContent>
    </Card>
  );
}

type ProductDraft = { code: string; name: string; credits: string; price_amount: string; currency: string; active: boolean; sort_order: string };
const toDraft = (p?: AdminProduct): ProductDraft => ({
  code: p?.code ?? "",
  name: p?.name ?? "",
  credits: p ? String(p.credits) : "",
  price_amount: p ? String(p.price_amount) : "",
  currency: p?.currency ?? "VND",
  active: p?.active ?? true,
  sort_order: p ? String(p.sort_order) : "0",
});

function Products() {
  const t = useTranslations("admin.system");
  const f = useFmt();
  const res = useApi<AdminProduct[] | { items: AdminProduct[] }>("/admin/products");
  const products = asArray(res.data);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("products")}</h2>
        </CardTitle>
        <ProductDialog onSaved={res.reload} />
      </CardHeader>
      <CardContent>
        {res.error ? (
          <ErrorState error={res.error} onRetry={res.reload} />
        ) : !products ? (
          <LoadingState />
        ) : !products.length ? (
          <EmptyState>{t("noProducts")}</EmptyState>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("p.code")}</TableHead>
                <TableHead>{t("p.name")}</TableHead>
                <TableHead className="text-right">{t("p.credits")}</TableHead>
                <TableHead className="text-right">{t("p.price")}</TableHead>
                <TableHead>{t("p.active")}</TableHead>
                <TableHead className="text-right">{t("p.sort")}</TableHead>
                <TableHead>
                  <span className="sr-only">{t("p.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <code>{p.code}</code>
                  </TableCell>
                  <TableCell>{p.name}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.credits}</TableCell>
                  <TableCell className="text-right tabular-nums">{f.money(p.price_amount, p.currency)}</TableCell>
                  <TableCell>
                    <Badge variant={p.active ? "secondary" : "outline"}>{p.active ? t("p.yes") : t("p.no")}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{p.sort_order}</TableCell>
                  <TableCell className="text-right">
                    <ProductDialog product={p} onSaved={res.reload} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/** Create (no product) or edit a product; saving is the confirmation step. */
function ProductDialog({ product, onSaved }: { product?: AdminProduct; onSaved: () => void }) {
  const t = useTranslations("admin.system");
  const [d, setD] = useState<ProductDraft>(() => toDraft(product));
  const activeId = useId();
  const body = {
    code: d.code.trim(),
    name: d.name.trim(),
    credits: Number(d.credits),
    price_amount: Number(d.price_amount),
    currency: d.currency.trim().toUpperCase(),
    active: d.active,
    sort_order: Number(d.sort_order),
  };
  const valid =
    body.code && body.name && body.currency.length === 3 && Number.isInteger(body.credits) && body.credits > 0 && body.price_amount >= 0 && d.price_amount !== "" && Number.isInteger(body.sort_order);

  return (
    <ConfirmDialog
      trigger={
        product ? (
          <Button size="sm" variant="outline">
            {t("p.edit")}
          </Button>
        ) : (
          <Button size="sm">
            <Plus aria-hidden />
            {t("p.new")}
          </Button>
        )
      }
      title={product ? t("p.editTitle", { code: product.code }) : t("p.newTitle")}
      description={product && !d.active && product.active ? t("p.deactivateWarning") : undefined}
      confirmLabel={t("p.save")}
      destructive={Boolean(product?.active && !d.active)}
      canConfirm={Boolean(valid)}
      onOpenChange={(o) => o && setD(toDraft(product))}
      onConfirm={async () => {
        if (product) await api(`/admin/products/${product.id}`, { method: "PATCH", json: diff(toBody(product), body) });
        else await api("/admin/products", { method: "POST", json: body });
        onSaved();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("p.code")} value={d.code} onChange={(e) => setD({ ...d, code: e.target.value })} required />
        <Field label={t("p.name")} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} required />
        <Field label={t("p.credits")} type="number" min={1} step={1} value={d.credits} onChange={(e) => setD({ ...d, credits: e.target.value })} required />
        <Field label={t("p.price")} hint={t("p.priceHint")} type="number" min={0} step={1} value={d.price_amount} onChange={(e) => setD({ ...d, price_amount: e.target.value })} required />
        <Field label={t("p.currency")} value={d.currency} maxLength={3} onChange={(e) => setD({ ...d, currency: e.target.value })} required />
        <Field label={t("p.sort")} type="number" step={1} value={d.sort_order} onChange={(e) => setD({ ...d, sort_order: e.target.value })} />
      </div>
      <div className="flex items-center gap-2">
        <Switch id={activeId} checked={d.active} onCheckedChange={(v) => setD({ ...d, active: v })} />
        <Label htmlFor={activeId}>{t("p.active")}</Label>
      </div>
    </ConfirmDialog>
  );
}

const toBody = (p: AdminProduct) => ({
  code: p.code,
  name: p.name,
  credits: p.credits,
  price_amount: p.price_amount,
  currency: p.currency,
  active: p.active,
  sort_order: p.sort_order,
});
