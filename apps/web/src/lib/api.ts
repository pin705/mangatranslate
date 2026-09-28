// Typed client for docs/API.md. Browser code calls same-origin /api/v1 (proxied by next.config rewrites);
// the HttpOnly session cookie travels automatically — never read or store tokens in JS.

export type Role = "USER" | "ADMIN" | "SUPER_ADMIN";
export type Locale = "vi" | "en";
export type Mode = "clean" | "overlay";

export interface User {
  id: string;
  email: string;
  email_verified: boolean;
  role: Role;
  locale: Locale;
  credits: number;
  created_at: string;
}

export const isAdmin = (u: Pick<User, "role">) => u.role === "ADMIN" || u.role === "SUPER_ADMIN";

export interface Product {
  code: string;
  name: string;
  credits: number;
  /** Extra promotional credits; a purchase grants credits + bonus_credits. */
  bonus_credits: number;
  price_amount: number;
  currency: string;
}

export interface Pricing {
  credits_per_page: Record<Mode, number>;
  signup_bonus: number;
  languages: { source: string[]; target: string[] };
  limits: { max_pages_per_job: number; max_upload_mb: number; max_concurrent_jobs: number };
  retention_days: number;
  /** Size of one pricing block; see pageBlocks() in upload-rules.ts. */
  credit_megapixels: number;
  referral_bonus: number;
}

export interface UploadTicket {
  id: string;
  upload_url: string;
  method: string;
  headers: Record<string, string>;
  expires_in: number;
}

export const JOB_STATUSES = [
  "PENDING", "INGESTING", "PROCESSING", "TRANSLATING", "RENDERING", "FINALIZING",
  "COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "EXPIRED",
] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];
export const TERMINAL: readonly JobStatus[] = ["COMPLETED", "PARTIAL", "FAILED", "CANCELLED", "EXPIRED"];
export const isTerminal = (s: JobStatus) => TERMINAL.includes(s);

export interface ErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export interface Job {
  id: string;
  series_id: string | null;
  title: string;
  status: JobStatus;
  source_lang: string;
  target_lang: string;
  mode: Mode;
  page_count: number;
  pages_done: number;
  pages_failed: number;
  pages_review: number;
  credits_reserved: number;
  credits_charged: number;
  error: ErrorBody | null;
  created_at: string;
  finished_at: string | null;
  expires_at: string | null;
}

export type PageStatus = "pending" | "processing" | "ready" | "failed";
export type ReviewReason = "LOW_OCR_CONFIDENCE" | "TRANSLATION_UNCERTAIN" | "TEXT_OVERFLOW" | "NO_TEXT_FOUND";

export interface PageSummary {
  id: string;
  index: number;
  status: PageStatus;
  stage: "none" | "prepared" | "translated" | "rendered";
  needs_review: boolean;
  review_reasons: ReviewReason[];
  width: number;
  height: number;
  source_url: string | null;
  output_url: string | null;
  error: ErrorBody | string | null;
  updated_at: string;
}

export type Alignment = "left" | "center" | "right";
export interface RegionStyle {
  font_size: number | null;
  alignment: Alignment;
  color: string;
  outline: boolean;
  uppercase: boolean;
}
export type BBox = [number, number, number, number];
export interface Region {
  id: string;
  bbox: BBox;
  text: string;
  translation: string;
  confidence: number;
  style: RegionStyle;
}

export interface PageDetail extends PageSummary {
  job_id: string;
  clean_url: string | null;
  regions: Region[];
  version: number;
}

export type CreditKind =
  | "signup_bonus" | "purchase" | "reserve" | "release" | "refund" | "admin_grant" | "admin_revoke" | "referral";
export interface CreditTransaction {
  id: string | number;
  amount: number;
  kind: CreditKind;
  reason: string | null;
  job_id: string | null;
  created_at: string;
}

export type PaymentStatus = "pending" | "paid" | "cancelled" | "failed" | "refunded";
export interface Payment {
  id: string;
  product_code: string;
  amount: number;
  currency: string;
  credits: number;
  status: PaymentStatus;
  created_at: string;
  paid_at: string | null;
}

export interface Term {
  source: string;
  target: string;
  /** Learned by the translator from a chapter; user terms (auto: false) always win. */
  auto: boolean;
}
export interface Series {
  id: string;
  title: string;
  source_lang: string;
  target_lang: string;
  chapters: number;
  terms: number;
  created_at: string;
  updated_at: string;
}
/** GET /series/{id}: in the detail response `chapters` is the chapter list (oldest first), not a count. */
export type SeriesDetail = Omit<Series, "chapters"> & { glossary: Term[]; chapters: Job[] };

export type ShareState =
  | { active: false }
  | { active: true; token_hint: string; created_at: string; expires_at: string; views: number; url: string | null };
export interface SharedChapter {
  title: string;
  source_lang: string;
  target_lang: string;
  expires_at: string;
  pages: { index: number; width: number; height: number; url: string }[];
}

export type NotificationKind =
  | "job_completed" | "job_failed" | "payment_succeeded" | "payment_failed" | "credits_low" | "referral_reward";
export interface AppNotification {
  id: number;
  kind: NotificationKind | string;
  data: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

export interface Referral {
  code: string;
  link: string;
  invited: number;
  rewarded: number;
  reward_credits: number;
}

export interface List<T> {
  items: T[];
  total: number;
}

// Admin
export type UserStatus = "active" | "suspended" | "deleted";
export interface AdminUser extends User {
  status: UserStatus;
}
export interface AdminMetrics {
  users: number;
  active_users_30d: number;
  jobs_by_status: Partial<Record<JobStatus, number>>;
  pages_processed: number;
  revenue: Record<string, number>;
  ai_cost_usd: number;
  gross_margin_usd: number;
  avg_cost_per_page_usd: number;
  avg_processing_seconds: number;
  failed_jobs_30d: number;
}
export interface CostRow {
  date: string;
  pages: number;
  ai_cost_usd: number;
  revenue_vnd: number;
}
export type AdminJob = Job & { user_email: string };
export type AdminPayment = Payment & { user_email: string; provider: string };
export interface AiProvider {
  id: string;
  kind: string;
  name: string;
  base_url: string;
  model: string;
  enabled: boolean;
  priority: number;
  input_price_per_1m: number;
  output_price_per_1m: number;
  healthy: boolean;
}
export interface AppSettings {
  credits_per_page_clean: number;
  credits_per_page_overlay: number;
  credit_megapixels: number;
  signup_bonus: number;
  referral_bonus: number;
  credits_low_threshold: number;
  max_monthly_ai_spend_usd: number;
  usd_vnd_rate: number;
  max_pages_per_job: number;
  max_concurrent_jobs: number;
  retention_days: number;
}
export interface AdminProduct extends Product {
  id: string;
  active: boolean;
  sort_order: number;
}
export interface AuditEntry {
  id: string | number;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  metadata: unknown;
  ip: string | null;
  created_at: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** fetch + the API error envelope. Network failures become code "NETWORK_ERROR" (status 0). */
export async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const e = body?.error;
    throw new ApiError(res.status, e?.code ?? "INTERNAL_ERROR", typeof e?.message === "string" ? e.message : "", e?.details ?? null);
  }
  return body as T;
}

type Options = Omit<RequestInit, "body"> & { json?: unknown };

/** Browser-side call to /api/v1{path}. */
export function api<T>(path: string, { json, headers, ...init }: Options = {}): Promise<T> {
  return request<T>(`/api/v1${path}`, {
    credentials: "same-origin",
    ...init,
    headers: json === undefined ? headers : { "Content-Type": "application/json", ...headers },
    body: json === undefined ? undefined : JSON.stringify(json),
  });
}

export function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** User-facing text for any thrown value: the API's safe message, else a translated fallback. */
/** Any next-intl translator scoped to "errors" (client or server). */
type ErrorsT = { (key: never): string; has(key: never): boolean };

/** Localized text for an error: known codes use the UI language; unknown codes fall back to the API's message. */
export function describeError(e: unknown, t: ErrorsT): string {
  const tr = t as unknown as { (key: string): string; has(key: string): boolean };
  if (e instanceof ApiError) {
    if (e.code === "NETWORK_ERROR") return tr("network");
    if (tr.has(`codes.${e.code}`)) return tr(`codes.${e.code}`);
    if (e.message) return e.message;
  }
  return tr("generic");
}

export const errorCode = (e: unknown) => (e instanceof ApiError ? e.code : null);
