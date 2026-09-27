"use client";

import { FileArchive, FileImage, Loader2, Upload, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useId, useRef, useState, type DragEvent } from "react";
import { ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useUser } from "@/components/user-context";
import { useApi } from "@/hooks/use-api";
import { useErrorText } from "@/hooks/use-error-text";
import { useLangName } from "@/hooks/use-lang-name";
import { api, ApiError, errorCode, type Job, type Mode, type Pricing, type UploadTicket } from "@/lib/api";
import { ACCEPT, checkFile, contentType, estimateCredits, isImage, parseGlossary } from "@/lib/upload-rules";
import { cn, uuid } from "@/lib/utils";

type Item = { key: string; file: File };

/** PUT the bytes to the signed URL with exactly the returned headers, reporting upload progress. */
function putFile(ticket: UploadTicket, file: File, onProgress: (pct: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(ticket.method || "PUT", ticket.upload_url);
    for (const [k, v] of Object.entries(ticket.headers ?? {})) {
      if (k.toLowerCase() !== "content-length") xhr.setRequestHeader(k, v); // browser sets Content-Length itself
    }
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new ApiError(xhr.status, "UPLOAD_FAILED", "")));
    xhr.onerror = () => reject(new ApiError(0, "UPLOAD_FAILED", ""));
    xhr.send(file);
  });
}

const stripExt = (name: string) => name.replace(/\.[^.]+$/, "");

export function NewTranslation({ compact = false }: { compact?: boolean }) {
  const pricing = useApi<Pricing>("/pricing");
  if (pricing.error) return <ErrorState error={pricing.error} onRetry={pricing.reload} />;
  if (!pricing.data) return <LoadingState rows={4} />;
  return <Form pricing={pricing.data} compact={compact} />;
}

function Form({ pricing, compact }: { pricing: Pricing; compact: boolean }) {
  const t = useTranslations("upload");
  const text = useErrorText();
  const langName = useLangName();
  const router = useRouter();
  const locale = useLocale();
  const { user, refresh } = useUser();
  const ids = { title: useId(), source: useId(), target: useId(), glossary: useId(), input: useId() };

  const { source: sources, target: targets } = pricing.languages;
  const preferredTarget = locale === "en" ? "English" : "Vietnamese";
  const [items, setItems] = useState<Item[]>([]);
  const [rejected, setRejected] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [source, setSource] = useState(sources[0] ?? "");
  const [target, setTarget] = useState(targets.includes(preferredTarget) ? preferredTarget : (targets[0] ?? ""));
  const [mode, setMode] = useState<Mode>("clean");
  const [glossary, setGlossary] = useState("");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [phase, setPhase] = useState<"idle" | "uploading" | "creating">("idle");
  const [error, setError] = useState<unknown>(null);

  // One Idempotency-Key per submission; kept across retries of the same form, reset when the form changes.
  const idemKey = useRef<string | null>(null);
  const uploaded = useRef(new Map<string, string>()); // item key -> upload id (skip re-uploading on retry)
  const touch = () => {
    idemKey.current = null;
    setError(null);
  };

  const { limits } = pricing;
  const names = items.map((i) => i.file.name);
  const est = estimateCredits(names, pricing.credits_per_page[mode]);
  const glossaryParsed = parseGlossary(glossary);
  const busy = phase !== "idle";

  function addFiles(list: FileList | null) {
    if (!list) return;
    const bad: string[] = [];
    const next: Item[] = [];
    for (const file of Array.from(list)) {
      const problem = checkFile(file.name, file.size, limits.max_upload_mb);
      if (problem) bad.push(t(`reject.${problem}`, { name: file.name, mb: limits.max_upload_mb }));
      else next.push({ key: `${file.name}:${file.size}:${file.lastModified}:${uuid()}`, file });
    }
    setRejected(bad);
    if (!next.length) return;
    const all = [...items, ...next].sort((a, b) => a.file.name.localeCompare(b.file.name, undefined, { numeric: true }));
    setItems(all);
    if (!title) setTitle(stripExt(all[0].file.name));
    uploaded.current.clear();
    touch();
  }

  function remove(key: string) {
    setItems((xs) => xs.filter((x) => x.key !== key));
    uploaded.current.clear();
    touch();
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!busy) addFiles(e.dataTransfer.files);
  }

  async function submit() {
    setError(null);
    if (!items.length) return setError(t("errors.noFiles"));
    if (est.images > limits.max_pages_per_job) return setError(t("errors.tooManyPages", { max: limits.max_pages_per_job }));
    if (glossaryParsed.invalid.length) return setError(t("errors.glossary", { lines: glossaryParsed.invalid.join(", ") }));
    if (!user.email_verified) return setError(new ApiError(403, "EMAIL_NOT_VERIFIED", ""));

    idemKey.current ??= uuid();
    const key = idemKey.current;
    try {
      setPhase("uploading");
      const queue = items.filter((i) => !uploaded.current.has(i.key));
      // ponytail: 3 parallel uploads; tune if storage throttles
      await Promise.all(
        Array.from({ length: Math.min(3, queue.length) }, async () => {
          for (let item = queue.shift(); item; item = queue.shift()) {
            const it = item;
            const ticket = await api<UploadTicket>("/uploads", {
              method: "POST",
              json: { filename: it.file.name, size: it.file.size, content_type: contentType(it.file.name) },
            });
            await putFile(ticket, it.file, (pct) => setProgress((p) => ({ ...p, [it.key]: pct })));
            uploaded.current.set(it.key, ticket.id);
          }
        }),
      );
      setPhase("creating");
      const job = await api<Job>("/jobs", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        json: {
          title: title.trim() || stripExt(items[0].file.name),
          upload_ids: items.map((i) => uploaded.current.get(i.key)),
          source_lang: source,
          target_lang: target,
          mode,
          glossary: glossaryParsed.entries,
        },
      });
      refresh();
      router.push(`/jobs/${job.id}`);
    } catch (e) {
      setError(e);
      setPhase("idle");
    }
  }

  const done = Object.values(progress).filter((p) => p === 100).length;
  const code = errorCode(error);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </CardTitle>
        {!compact && <CardDescription>{t("description")}</CardDescription>}
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (!busy) submit();
          }}
        >
          <div>
            <label
              htmlFor={ids.input}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-center text-sm transition focus-within:ring-3 focus-within:ring-ring/50 hover:bg-muted/50",
                dragging && "border-primary bg-primary/5",
                busy && "pointer-events-none opacity-60",
              )}
            >
              <Upload className="size-6 text-muted-foreground" aria-hidden />
              <span className="font-medium">{t("dropHere")}</span>
              <span className="text-muted-foreground">{t("formats", { mb: limits.max_upload_mb, pages: limits.max_pages_per_job })}</span>
              <input
                id={ids.input}
                type="file"
                multiple
                accept={ACCEPT}
                className="sr-only"
                disabled={busy}
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
            {rejected.length > 0 && (
              <ul role="alert" className="mt-2 space-y-1 text-sm text-destructive">
                {rejected.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
          </div>

          {items.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium">{t("selected", { count: items.length })}</p>
              <ul className="max-h-56 space-y-2 overflow-y-auto pr-1">
                {items.map((it) => {
                  const pct = progress[it.key];
                  return (
                    <li key={it.key} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                      {isImage(it.file.name) ? (
                        <FileImage className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                      ) : (
                        <FileArchive className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                      )}
                      <span className="min-w-0 flex-1 truncate">{it.file.name}</span>
                      {pct !== undefined ? (
                        <Progress value={pct} className="w-24" aria-label={t("fileProgress", { name: it.file.name })} />
                      ) : (
                        <span className="text-xs text-muted-foreground">{(it.file.size / 1048576).toFixed(1)} MB</span>
                      )}
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        disabled={busy}
                        onClick={() => remove(it.key)}
                        aria-label={t("remove", { name: it.file.name })}
                      >
                        <X aria-hidden />
                      </Button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5 sm:col-span-2">
              <Label htmlFor={ids.title}>{t("chapterTitle")}</Label>
              <Input
                id={ids.title}
                value={title}
                maxLength={200}
                placeholder={t("chapterPlaceholder")}
                onChange={(e) => {
                  setTitle(e.target.value);
                  touch();
                }}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={ids.source}>{t("sourceLang")}</Label>
              <Select
                value={source}
                onValueChange={(v) => {
                  setSource(v);
                  touch();
                }}
              >
                <SelectTrigger id={ids.source} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {sources.map((l) => (
                    <SelectItem key={l} value={l}>
                      {langName(l)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={ids.target}>{t("targetLang")}</Label>
              <Select
                value={target}
                onValueChange={(v) => {
                  setTarget(v);
                  touch();
                }}
              >
                <SelectTrigger id={ids.target} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {targets.map((l) => (
                    <SelectItem key={l} value={l}>
                      {langName(l)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium">{t("mode")}</legend>
            <RadioGroup
              value={mode}
              onValueChange={(v) => {
                setMode(v as Mode);
                touch();
              }}
              className="grid gap-2 sm:grid-cols-2"
            >
              {(["clean", "overlay"] as const).map((m) => (
                <Label key={m} className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal has-data-[state=checked]:border-primary">
                  <RadioGroupItem value={m} className="mt-0.5" />
                  <span className="grid gap-0.5">
                    <span className="font-medium">{t(`modes.${m}.label`)}</span>
                    <span className="text-xs text-muted-foreground">
                      {t(`modes.${m}.hint`)} · {t("perPage", { count: pricing.credits_per_page[m] })}
                    </span>
                  </span>
                </Label>
              ))}
            </RadioGroup>
          </fieldset>

          <div className="grid gap-1.5">
            <Label htmlFor={ids.glossary}>{t("glossary")}</Label>
            <Textarea
              id={ids.glossary}
              value={glossary}
              rows={compact ? 2 : 3}
              placeholder={t("glossaryPlaceholder")}
              aria-describedby={`${ids.glossary}-hint`}
              onChange={(e) => {
                setGlossary(e.target.value);
                touch();
              }}
              className="font-mono text-sm"
            />
            <p id={`${ids.glossary}-hint`} className="text-xs text-muted-foreground">
              {t("glossaryHint")}
            </p>
          </div>

          <div className="rounded-lg bg-muted/60 p-3 text-sm" aria-live="polite">
            {items.length === 0 ? (
              <p className="text-muted-foreground">{t("estimateEmpty")}</p>
            ) : (
              <>
                <p>
                  {t("estimate", { pages: est.images, credits: est.credits })}
                  {est.hasArchives && ` ${t("archiveNote")}`}
                </p>
                <p className="text-muted-foreground">{t("balance", { credits: user.credits })}</p>
                {est.credits > user.credits && (
                  <p className="mt-1 text-amber-700 dark:text-amber-300">
                    {t("lowBalance")}{" "}
                    <Link href="/billing" className="underline underline-offset-4">
                      {t("buyCredits")}
                    </Link>
                  </p>
                )}
              </>
            )}
          </div>

          <div aria-live="polite" className="text-sm">
            {phase === "uploading" && <p>{t("uploading", { done, total: items.length })}</p>}
            {phase === "creating" && <p>{t("creating")}</p>}
          </div>

          {error !== null && (
            <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {code === "INSUFFICIENT_CREDITS" ? (
                <p>
                  {t("errors.insufficient")}{" "}
                  <Link href="/billing" className="font-medium underline underline-offset-4">
                    {t("buyCredits")}
                  </Link>
                </p>
              ) : code === "EMAIL_NOT_VERIFIED" ? (
                <p>{t("errors.notVerified")}</p>
              ) : code === "UPLOAD_FAILED" ? (
                <p>{t("errors.uploadFailed")}</p>
              ) : (
                <p>{typeof error === "string" ? error : text(error)}</p>
              )}
            </div>
          )}

          <Button type="submit" size="lg" disabled={busy || items.length === 0}>
            {busy && <Loader2 className="animate-spin" aria-hidden />}
            {busy ? t("working") : t("submit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
