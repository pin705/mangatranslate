"use client";

import {
  AlertTriangle,
  AlignCenter,
  AlignLeft,
  AlignRight,
  CheckCircle2,
  ChevronDown,
  Clock,
  Loader2,
  Maximize,
  Redo2,
  Save,
  SquareDashed,
  Undo2,
  XCircle,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode, type RefObject } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useUser } from "@/components/user-context";
import { useApi } from "@/hooks/use-api";
import { useErrorText } from "@/hooks/use-error-text";
import {
  api,
  errorCode,
  type Alignment,
  type BBox,
  type Job,
  type PageDetail,
  type PageSummary,
  type Pricing,
  type Region,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const MIN_BOX = 8; // source pixels
const HISTORY = 100;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);
const same = (a: Region[], b: Region[]) => JSON.stringify(a) === JSON.stringify(b);
const isTyping = (el: Element | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

// ---------------------------------------------------------------------------------------------
// Shell: loads the job's pages and switches between them (each page gets a fresh workspace).

export function Editor({ jobId, pageId }: { jobId: string; pageId?: string }) {
  const t = useTranslations("editor");
  const job = useApi<Job>(`/jobs/${jobId}`);
  const pages = useApi<PageSummary[]>(`/jobs/${jobId}/pages`);
  const pricing = useApi<Pricing>("/pricing");
  const [chosen, setChosen] = useState(pageId);
  const dirtyRef = useRef(false);

  const error = job.error ?? pages.error;
  if (error) return <ErrorState error={error} onRetry={() => (job.reload(), pages.reload())} />;
  if (!job.data || !pages.data) return <LoadingState rows={8} />;
  const list = pages.data;
  const current = list.find((p) => p.id === chosen) ?? list.find((p) => p.status === "ready") ?? list[0];
  if (!current) return <EmptyState>{t("noPages")}</EmptyState>;

  const confirmLeave = () => !dirtyRef.current || window.confirm(t("unsaved"));
  function switchTo(id: string) {
    if (id === current.id || !confirmLeave()) return;
    dirtyRef.current = false;
    setChosen(id);
    window.history.replaceState(null, "", `?page=${id}`);
  }

  const sidebar = (
    <nav aria-label={t("pageList")} className="shrink-0 overflow-auto border-b lg:w-36 lg:border-r lg:border-b-0">
      <ol className="flex gap-1 p-2 lg:flex-col">
        {list.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => switchTo(p.id)}
              aria-current={p.id === current.id ? "page" : undefined}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm whitespace-nowrap hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                p.id === current.id && "bg-muted font-medium",
              )}
            >
              <PageIcon page={p} />
              {t("pageN", { n: p.index + 1 })}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:h-[calc(100dvh-6.5rem)] lg:flex-row">
      {sidebar}
      <PageEditor
        key={current.id}
        jobId={jobId}
        page={current}
        total={list.length}
        regenCost={pricing.data?.credits_per_page[job.data.mode]}
        dirtyRef={dirtyRef}
        confirmLeave={confirmLeave}
        onUpdated={(d) => pages.setData(list.map((p) => (p.id === d.id ? { ...p, ...d } : p)))}
      />
    </div>
  );
}

function PageIcon({ page }: { page: PageSummary }) {
  const t = useTranslations("pageStatus");
  const [Icon, cls, label] =
    page.status === "failed"
      ? [XCircle, "text-destructive", t("failed")]
      : page.status === "ready" && page.needs_review
        ? [AlertTriangle, "text-amber-600", t("review")]
        : page.status === "ready"
          ? [CheckCircle2, "text-emerald-600", t("ready")]
          : page.status === "processing"
            ? [Loader2, "animate-spin text-sky-600", t("processing")]
            : [Clock, "text-muted-foreground", t("pending")];
  return (
    <>
      <Icon className={cn("size-4 shrink-0", cls)} aria-hidden />
      <span className="sr-only">{label}:</span>
    </>
  );
}

type PageEditorProps = {
  jobId: string;
  page: PageSummary;
  total: number;
  regenCost?: number;
  dirtyRef: RefObject<boolean>;
  confirmLeave: () => boolean;
  onUpdated: (d: PageDetail) => void;
};

/** Loads one page; a conflict reload remounts the workspace from fresh server state. */
function PageEditor(props: PageEditorProps) {
  const detail = useApi<PageDetail>(`/pages/${props.page.id}`);
  const [generation, setGeneration] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  if (detail.error) return <div className="flex-1 p-4"><ErrorState error={detail.error} onRetry={detail.reload} /></div>;
  if (!detail.data || detail.loading) return <div className="flex-1 p-4"><LoadingState rows={6} /></div>;
  return (
    <Workspace
      key={generation}
      {...props}
      initial={detail.data}
      initialNotice={notice}
      onReload={(msg) => {
        setNotice(msg);
        detail.reload();
        setGeneration((g) => g + 1);
      }}
    />
  );
}

// ---------------------------------------------------------------------------------------------
// Workspace: canvas + region panel + toolbar for one page.

type Drag = {
  kind: "move" | "resize" | "pan";
  id?: string;
  x: number;
  y: number;
  bbox?: BBox;
  pan?: { x: number; y: number };
  before?: Region[];
  moved: boolean;
};
type Notice = { kind: "info" | "error" | "success"; text: string; billing?: boolean } | null;
type ImageView = "original" | "clean" | "output";

function Workspace({
  jobId,
  page,
  total,
  regenCost,
  dirtyRef,
  confirmLeave,
  onUpdated,
  initial,
  initialNotice,
  onReload,
}: PageEditorProps & { initial: PageDetail; initialNotice: string | null; onReload: (notice: string) => void }) {
  const t = useTranslations("editor");
  const text = useErrorText();
  const { refresh: refreshUser } = useUser();

  const [detail, setDetail] = useState(initial);
  const [regions, setRegions] = useState(initial.regions);
  const [hist, setHist] = useState<{ past: Region[][]; future: Region[][]; lastKey: string | null }>({
    past: [],
    future: [],
    lastKey: null,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [manualView, setManualView] = useState<{ zoom: number; x: number; y: number } | null>(null); // null = fit
  const [imageView, setImageView] = useState<ImageView>(initial.output_url ? "output" : "original");
  const [showBoxes, setShowBoxes] = useState(true);
  const [space, setSpace] = useState(false);
  const [busy, setBusy] = useState<null | "saving" | "rendering">(null);
  const [notice, setNotice] = useState<Notice>(initialNotice ? { kind: "error", text: initialNotice } : null);
  const [regen, setRegen] = useState<null | "translation" | "inpaint">(null);
  const drag = useRef<Drag | null>(null);
  const alive = useRef(true);

  const viewportRef = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width: w, height: h } = entry.contentRect;
      setSize((s) => (s.w === w && s.h === h ? s : { w, h }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const W = detail.width || natural?.w || 1000;
  const H = detail.height || natural?.h || 1400;
  const dirty = useMemo(() => !same(regions, detail.regions), [regions, detail.regions]);
  const editable = detail.status === "ready";
  const sel = regions.find((r) => r.id === selected) ?? null;

  const fit = useMemo(() => {
    if (!size.w || !size.h) return { zoom: 1, x: 0, y: 0 };
    const zoom = Math.max(0.05, Math.min((size.w - 32) / W, (size.h - 32) / H));
    return { zoom, x: (size.w - W * zoom) / 2, y: (size.h - H * zoom) / 2 };
  }, [size, W, H]);
  const view = manualView ?? fit;
  const z = view.zoom;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty, dirtyRef]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // --- history -------------------------------------------------------------------------------
  function pushHistory(before: Region[], key?: string) {
    setHist((h) =>
      key && h.lastKey === key ? h : { past: [...h.past.slice(-HISTORY + 1), before], future: [], lastKey: key ?? null },
    );
  }
  /** Replace regions as one undo step; consecutive commits with the same key (typing, nudging) merge. */
  function commit(next: Region[], key?: string) {
    pushHistory(regions, key);
    setRegions(next);
  }
  const update = (id: string, fn: (r: Region) => Region, key?: string) =>
    commit(regions.map((r) => (r.id === id ? fn(r) : r)), key);
  const setStyle = (id: string, patch: Partial<Region["style"]>, key?: string) =>
    update(id, (r) => ({ ...r, style: { ...r.style, ...patch } }), key);

  function undo() {
    const prev = hist.past.at(-1);
    if (!prev) return;
    setHist({ past: hist.past.slice(0, -1), future: [regions, ...hist.future], lastKey: null });
    setRegions(prev);
  }
  function redo() {
    const [next, ...rest] = hist.future;
    if (!next) return;
    setHist({ past: [...hist.past, regions], future: rest, lastKey: null });
    setRegions(next);
  }
  function nudge(dx: number, dy: number) {
    if (!sel || !editable) return;
    const [x1, y1, x2, y2] = sel.bbox;
    const nx = clamp(x1 + dx, 0, W - (x2 - x1));
    const ny = clamp(y1 + dy, 0, H - (y2 - y1));
    update(sel.id, (r) => ({ ...r, bbox: [nx, ny, nx + (x2 - x1), ny + (y2 - y1)] }), `nudge:${sel.id}`);
  }

  // --- view ----------------------------------------------------------------------------------
  function zoomBy(f: number) {
    const nz = clamp(z * f, 0.05, 8);
    const cx = size.w / 2;
    const cy = size.h / 2;
    setManualView({ zoom: nz, x: cx - (cx - view.x) * (nz / z), y: cy - (cy - view.y) * (nz / z) });
  }

  // --- save / render polling -----------------------------------------------------------------
  /** After a 202, poll until the page's version (or row) changes and it is no longer processing. */
  async function waitForRender(base: PageDetail) {
    setBusy("rendering");
    setNotice({ kind: "info", text: t("rendering") });
    for (let i = 0; i < 60 && alive.current; i++) {
      await sleep(2000);
      let p: PageDetail;
      try {
        p = await api<PageDetail>(`/pages/${page.id}`);
      } catch {
        continue; // transient; keep polling
      }
      if (!alive.current) return;
      const changed = p.version !== base.version || p.updated_at !== base.updated_at;
      if (changed && p.status !== "processing" && p.status !== "pending") {
        setDetail(p);
        setRegions((cur) => (same(cur, base.regions) ? p.regions : cur)); // keep edits made meanwhile
        onUpdated(p);
        setBusy(null);
        setNotice(p.status === "failed" ? { kind: "error", text: t("renderFailed") } : { kind: "success", text: t("updated") });
        return;
      }
    }
    if (alive.current) {
      setBusy(null);
      setNotice({ kind: "info", text: t("renderSlow") });
    }
  }

  async function run(fn: () => Promise<void>) {
    setNotice(null);
    try {
      await fn();
    } catch (e) {
      setBusy(null);
      const code = errorCode(e);
      if (code === "CONFLICT") {
        onReload(t("conflict"));
      } else {
        setNotice({ kind: "error", text: code === "INSUFFICIENT_CREDITS" ? t("insufficient") : text(e), billing: code === "INSUFFICIENT_CREDITS" });
      }
    }
  }

  const save = () =>
    run(async () => {
      if (!dirty || busy || !editable) return;
      setBusy("saving");
      const d = await api<PageDetail>(`/pages/${page.id}/regions`, {
        method: "PUT",
        json: { regions, version: detail.version },
      });
      setDetail(d);
      setRegions((cur) => (same(cur, regions) ? d.regions : cur));
      setHist((h) => ({ ...h, lastKey: null }));
      await waitForRender(d);
    });

  const regenerate = (what: "typeset" | "translation" | "inpaint") =>
    run(async () => {
      setBusy("rendering");
      const d = await api<PageDetail>(`/pages/${page.id}/regenerate`, { method: "POST", json: { what } });
      if (what !== "typeset") refreshUser();
      setDetail((cur) => ({ ...d, regions: cur.regions })); // regions update when rendering finishes
      await waitForRender({ ...d, regions });
    });

  // --- keyboard ------------------------------------------------------------------------------
  const keys = useRef({ undo, redo, save, nudge, zoomBy, fit: () => setManualView(null), deselect: () => setSelected(null) });
  useEffect(() => {
    keys.current = { undo, redo, save, nudge, zoomBy, fit: () => setManualView(null), deselect: () => setSelected(null) };
  });
  useEffect(() => {
    function down(e: KeyboardEvent) {
      const k = keys.current;
      const mod = e.ctrlKey || e.metaKey;
      const typing = isTyping(document.activeElement);
      if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        k.save();
        return;
      }
      if (e.key === "Escape") {
        if (typing) (document.activeElement as HTMLElement).blur();
        k.deselect();
        return;
      }
      if (typing) return; // let inputs keep native undo, arrows, space
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) k.redo();
        else k.undo();
      } else if (mod && e.key.toLowerCase() === "y") {
        e.preventDefault();
        k.redo();
      } else if (e.key.startsWith("Arrow")) {
        const step = e.shiftKey ? 10 : 1;
        const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
        if (d) {
          e.preventDefault();
          k.nudge(d[0], d[1]);
        }
      } else if (e.key === " " && !(document.activeElement instanceof HTMLButtonElement)) {
        e.preventDefault();
        setSpace(true);
      } else if (!mod && (e.key === "+" || e.key === "=")) k.zoomBy(1.25);
      else if (!mod && e.key === "-") k.zoomBy(0.8);
      else if (!mod && e.key === "0") k.fit();
    }
    const up = (e: KeyboardEvent) => e.key === " " && setSpace(false);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  // --- pointer -------------------------------------------------------------------------------
  function startRegionDrag(e: ReactPointerEvent, r: Region, kind: "move" | "resize") {
    if (space || e.button !== 0) return; // space+drag pans even over regions
    e.stopPropagation();
    setSelected(r.id);
    if (!editable) return;
    (e.currentTarget.closest("[data-viewport]") as HTMLElement | null)?.setPointerCapture(e.pointerId);
    drag.current = { kind, id: r.id, x: e.clientX, y: e.clientY, bbox: r.bbox, before: regions, moved: false };
  }
  function onViewportDown(e: ReactPointerEvent<HTMLDivElement>) {
    if (e.button !== 0 && e.button !== 1) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { kind: "pan", x: e.clientX, y: e.clientY, pan: { x: view.x, y: view.y }, moved: false };
  }
  function onMove(e: ReactPointerEvent) {
    const d = drag.current;
    if (!d) return;
    const px = e.clientX - d.x;
    const py = e.clientY - d.y;
    if (Math.abs(px) + Math.abs(py) > 2) d.moved = true;
    if (d.kind === "pan" && d.pan) {
      setManualView({ zoom: z, x: d.pan.x + px, y: d.pan.y + py });
      return;
    }
    if (!d.bbox || !d.id) return;
    const dx = px / z;
    const dy = py / z;
    const [x1, y1, x2, y2] = d.bbox;
    let nb: BBox;
    if (d.kind === "move") {
      const nx = Math.round(clamp(x1 + dx, 0, W - (x2 - x1)));
      const ny = Math.round(clamp(y1 + dy, 0, H - (y2 - y1)));
      nb = [nx, ny, nx + (x2 - x1), ny + (y2 - y1)];
    } else {
      nb = [x1, y1, Math.round(clamp(x2 + dx, x1 + MIN_BOX, W)), Math.round(clamp(y2 + dy, y1 + MIN_BOX, H))];
    }
    const id = d.id;
    setRegions((rs) => rs.map((r) => (r.id === id ? { ...r, bbox: nb } : r)));
  }
  function onUp() {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.kind === "pan" && !d.moved) setSelected(null);
    else if (d.kind !== "pan" && d.moved && d.before) pushHistory(d.before);
  }

  // --- render --------------------------------------------------------------------------------
  const src =
    imageView === "original" ? detail.source_url : imageView === "clean" ? (detail.clean_url ?? detail.source_url) : (detail.output_url ?? detail.source_url);
  const status = busy === "saving" ? t("saving") : busy === "rendering" ? t("rendering") : dirty ? t("unsavedShort") : t("allSaved");

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {/* Toolbar */}
      <div role="toolbar" aria-label={t("toolbar")} className="flex flex-wrap items-center gap-1 border-b px-2 py-1.5">
        <Link
          href={`/jobs/${jobId}`}
          onClick={(e) => !confirmLeave() && e.preventDefault()}
          className="mr-1 rounded-md px-2 py-1 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          ← {t("back")}
        </Link>
        <span className="mr-2 text-sm font-medium">{t("pageOf", { n: page.index + 1, total })}</span>
        <Sep />
        <ToolButton label={t("undo")} shortcut="Ctrl+Z" onClick={undo} disabled={!hist.past.length}>
          <Undo2 />
        </ToolButton>
        <ToolButton label={t("redo")} shortcut="Ctrl+Shift+Z" onClick={redo} disabled={!hist.future.length}>
          <Redo2 />
        </ToolButton>
        <Sep />
        <ToolButton label={t("zoomOut")} shortcut="-" onClick={() => zoomBy(0.8)}>
          <ZoomOut />
        </ToolButton>
        <span className="w-12 text-center text-xs tabular-nums" aria-live="polite">
          {Math.round(z * 100)}%
        </span>
        <ToolButton label={t("zoomIn")} shortcut="+" onClick={() => zoomBy(1.25)}>
          <ZoomIn />
        </ToolButton>
        <ToolButton label={t("fit")} shortcut="0" onClick={() => setManualView(null)}>
          <Maximize />
        </ToolButton>
        <Sep />
        <div role="group" aria-label={t("imageView")} className="inline-flex rounded-lg border p-0.5">
          {(["original", "clean", "output"] as const).map((v) => (
            <Button
              key={v}
              size="xs"
              variant={imageView === v ? "secondary" : "ghost"}
              aria-pressed={imageView === v}
              disabled={(v === "clean" && !detail.clean_url) || (v === "output" && !detail.output_url)}
              onClick={() => setImageView(v)}
            >
              {t(`views.${v}`)}
            </Button>
          ))}
        </div>
        <ToolButton label={t("boxes")} onClick={() => setShowBoxes((b) => !b)} pressed={showBoxes}>
          <SquareDashed />
        </ToolButton>
        <div className="ml-auto flex items-center gap-2">
          <span aria-live="polite" className="hidden text-xs text-muted-foreground sm:inline">
            {status}
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="outline" disabled={!editable || dirty || busy !== null} title={dirty ? t("saveFirst") : undefined}>
                {t("regenerate")}
                <ChevronDown aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuItem onSelect={() => regenerate("typeset")} className="flex-col items-start gap-0">
                <span>{t("regen.typeset")}</span>
                <span className="text-xs text-muted-foreground">{t("regen.free")}</span>
              </DropdownMenuItem>
              {(["translation", "inpaint"] as const).map((w) => (
                <DropdownMenuItem key={w} onSelect={() => setRegen(w)} className="flex-col items-start gap-0">
                  <span>{t(`regen.${w}`)}</span>
                  <span className="text-xs text-muted-foreground">{t("regen.costs", { count: regenCost ?? 1 })}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button size="sm" onClick={save} disabled={!dirty || busy !== null || !editable}>
            {busy === "saving" ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />}
            {t("save")}
          </Button>
        </div>
      </div>

      {(notice || !editable) && (
        <div
          role={notice?.kind === "error" ? "alert" : "status"}
          className={cn(
            "border-b px-3 py-1.5 text-sm",
            notice?.kind === "error" ? "bg-destructive/10 text-destructive" : notice?.kind === "success" ? "bg-emerald-600/10" : "bg-muted",
          )}
        >
          {notice ? notice.text : t("notEditable")}
          {notice?.billing && (
            <Link href="/billing" className="ml-2 font-medium underline underline-offset-4">
              {t("buyCredits")}
            </Link>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Canvas */}
        <div
          data-viewport
          ref={viewportRef}
          onPointerDown={onViewportDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
          className={cn(
            "relative h-[60vh] min-w-0 touch-none overflow-hidden bg-muted/60 select-none lg:h-auto lg:flex-1",
            space ? "cursor-grab active:cursor-grabbing" : "cursor-default",
          )}
        >
          <div className="absolute top-0 left-0" style={{ transform: `translate(${view.x}px, ${view.y}px)`, width: W * z, height: H * z }}>
            {src && (
              <img
                src={src}
                alt={t("pageImage", { n: page.index + 1 })}
                draggable={false}
                onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
                className="pointer-events-none absolute inset-0 size-full bg-white"
              />
            )}
            {showBoxes &&
              regions.map((r, i) => {
                const [x1, y1, x2, y2] = r.bbox;
                const isSel = r.id === selected;
                return (
                  <div
                    key={r.id}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSel}
                    aria-label={t("regionLabel", { n: i + 1, text: r.translation || r.text })}
                    onPointerDown={(e) => startRegionDrag(e, r, "move")}
                    onFocus={() => setSelected(r.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") setSelected(r.id);
                    }}
                    className={cn(
                      "absolute border-2 outline-none focus-visible:ring-3 focus-visible:ring-ring/60",
                      editable && "cursor-move",
                      isSel ? "border-primary bg-primary/10" : "border-sky-500/80 hover:bg-sky-500/10",
                    )}
                    style={{ left: x1 * z, top: y1 * z, width: (x2 - x1) * z, height: (y2 - y1) * z }}
                  >
                    <span className="absolute -top-4 left-0 rounded-sm bg-sky-600 px-1 text-[10px] leading-4 text-white">{i + 1}</span>
                    {isSel && editable && (
                      <span
                        aria-hidden
                        onPointerDown={(e) => startRegionDrag(e, r, "resize")}
                        className="absolute -right-2 -bottom-2 size-4 cursor-se-resize rounded-sm border-2 border-primary bg-background"
                      />
                    )}
                  </div>
                );
              })}
          </div>
        </div>

        {/* Region panel */}
        <aside aria-label={t("panel")} className="shrink-0 overflow-y-auto border-t p-4 lg:w-80 lg:border-t-0 lg:border-l">
          {sel ? (
            <RegionForm
              key={sel.id}
              region={sel}
              n={regions.indexOf(sel) + 1}
              disabled={!editable}
              onText={(v) => update(sel.id, (r) => ({ ...r, translation: v }), `text:${sel.id}`)}
              onStyle={(patch, key) => setStyle(sel.id, patch, key && `${key}:${sel.id}`)}
              onClose={() => setSelected(null)}
            />
          ) : (
            <div className="space-y-4 text-sm">
              <p className="text-muted-foreground">{regions.length ? t("selectHint") : t("noRegions")}</p>
              {regions.length > 0 && (
                <ol className="space-y-1">
                  {regions.map((r, i) => (
                    <li key={r.id}>
                      <button
                        type="button"
                        onClick={() => setSelected(r.id)}
                        className="w-full truncate rounded-md px-2 py-1 text-left hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                      >
                        <span className="mr-2 text-muted-foreground tabular-nums">{i + 1}.</span>
                        {r.translation || r.text}
                      </button>
                    </li>
                  ))}
                </ol>
              )}
              <div className="rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground">
                <p className="mb-1 font-medium text-foreground">{t("shortcutsTitle")}</p>
                <ul className="space-y-0.5">
                  {(t.raw("shortcuts") as string[]).map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </aside>
      </div>

      <ConfirmDialog
        open={regen !== null}
        onOpenChange={(o) => !o && setRegen(null)}
        title={regen ? t(`regen.${regen}`) : ""}
        description={t("regen.confirm", { count: regenCost ?? 1 })}
        confirmLabel={t("regenerate")}
        onConfirm={() => {
          const w = regen;
          setRegen(null);
          if (w) regenerate(w);
        }}
      />
    </div>
  );
}

function Sep() {
  return <span aria-hidden className="mx-1 h-5 w-px bg-border" />;
}

function ToolButton({
  label,
  shortcut,
  pressed,
  children,
  ...props
}: { label: string; shortcut?: string; pressed?: boolean; children: ReactNode } & Omit<React.ComponentProps<typeof Button>, "children">) {
  return (
    <Button
      size="icon-sm"
      variant={pressed ? "secondary" : "ghost"}
      aria-label={label}
      aria-pressed={pressed}
      aria-keyshortcuts={shortcut}
      title={shortcut ? `${label} (${shortcut})` : label}
      {...props}
    >
      {children}
    </Button>
  );
}

function RegionForm({
  region,
  n,
  disabled,
  onText,
  onStyle,
  onClose,
}: {
  region: Region;
  n: number;
  disabled: boolean;
  onText: (v: string) => void;
  onStyle: (patch: Partial<Region["style"]>, coalesceKey?: string) => void;
  onClose: () => void;
}) {
  const t = useTranslations("editor");
  const s = region.style;
  const aligns: [Alignment, typeof AlignLeft][] = [
    ["left", AlignLeft],
    ["center", AlignCenter],
    ["right", AlignRight],
  ];
  return (
    <fieldset disabled={disabled} aria-labelledby="rf-title" className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 id="rf-title" className="font-semibold">
          {t("region", { n })}
        </h2>
        <Button type="button" size="xs" variant="ghost" onClick={onClose} aria-keyshortcuts="Escape">
          {t("deselect")}
        </Button>
      </div>
      <div className="grid gap-1.5">
        <span className="text-sm font-medium">{t("sourceText")}</span>
        <p className="rounded-md bg-muted p-2 text-sm whitespace-pre-wrap" lang="und">
          {region.text || "—"}
        </p>
        <span className="text-xs text-muted-foreground">
          {t("confidence", { pct: Math.round((region.confidence ?? 0) * 100) })}
        </span>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="rf-translation">{t("translation")}</Label>
        <Textarea id="rf-translation" rows={4} value={region.translation} onChange={(e) => onText(e.target.value)} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="rf-size">{t("fontSize")}</Label>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={s.font_size === null} onCheckedChange={(c) => onStyle({ font_size: c === true ? null : 24 })} />
            {t("auto")}
          </label>
          <Input
            id="rf-size"
            type="number"
            min={6}
            max={300}
            className="w-24"
            disabled={disabled || s.font_size === null}
            value={s.font_size ?? ""}
            onChange={(e) => {
              const v = e.target.valueAsNumber;
              if (Number.isFinite(v)) onStyle({ font_size: clamp(Math.round(v), 6, 300) }, "font");
            }}
          />
        </div>
      </div>
      <div className="grid gap-1.5">
        <span className="text-sm font-medium" id="rf-align">
          {t("alignment")}
        </span>
        <div role="group" aria-labelledby="rf-align" className="inline-flex w-fit rounded-lg border p-0.5">
          {aligns.map(([a, Icon]) => (
            <Button
              key={a}
              type="button"
              size="icon-sm"
              variant={s.alignment === a ? "secondary" : "ghost"}
              aria-pressed={s.alignment === a}
              aria-label={t(`align.${a}`)}
              onClick={() => onStyle({ alignment: a })}
            >
              <Icon aria-hidden />
            </Button>
          ))}
        </div>
      </div>
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="rf-color">{t("color")}</Label>
        <input
          id="rf-color"
          type="color"
          value={/^#[0-9a-f]{6}$/i.test(s.color) ? s.color : "#000000"}
          onChange={(e) => onStyle({ color: e.target.value }, "color")}
          className="h-8 w-14 cursor-pointer rounded-md border bg-background p-0.5"
        />
      </div>
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="rf-outline">{t("outline")}</Label>
        <Switch id="rf-outline" checked={s.outline} onCheckedChange={(v) => onStyle({ outline: v })} />
      </div>
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="rf-upper">{t("uppercase")}</Label>
        <Switch id="rf-upper" checked={s.uppercase} onCheckedChange={(v) => onStyle({ uppercase: v })} />
      </div>
    </fieldset>
  );
}
