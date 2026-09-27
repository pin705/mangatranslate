# API v1

Base path: `/api/v1`. JSON in and out. The live schema is served by FastAPI at `/api/openapi.json` (docs at `/api/docs` outside production); this file is the human-readable contract.

## Conventions

- **Auth**: server-side session in an `HttpOnly`, `SameSite=Lax` cookie named `mt_session` (`Secure` in production). Browser clients call the API same-origin (the web app proxies `/api/*`), so no token handling in JS.
- **CSRF**: unsafe methods (`POST/PUT/PATCH/DELETE`) with a session cookie are rejected when the `Origin` header is present and not in `CORS_ORIGINS`.
- **Errors**: every non-2xx response has the shape
  ```json
  { "error": { "code": "INSUFFICIENT_CREDITS", "message": "Not enough credits.", "details": null } }
  ```
  Codes used: `VALIDATION_ERROR` (422, `details` = field errors), `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `NOT_FOUND` (404), `CONFLICT` (409), `RATE_LIMITED` (429), `EMAIL_NOT_VERIFIED` (403), `INSUFFICIENT_CREDITS` (402), `INVALID_CREDENTIALS` (401), `ACCOUNT_SUSPENDED` (403), `INVALID_TOKEN` (400), `UPLOAD_INVALID` (400), `UPLOAD_MISSING` (400), `LIMIT_EXCEEDED` (400), `PAYMENT_PROVIDER_ERROR` (502), `INTERNAL_ERROR` (500). Messages are safe to show to users; stack traces are never returned.
- **Lists** use offset pagination: `?limit=20&offset=0` → `{ "items": [...], "total": 123 }`.
- **Timestamps** are ISO-8601 UTC strings. IDs are UUID strings unless noted.

## Health (no `/api/v1` prefix)

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `{ "status": "ok" }` — process alive |
| GET | `/ready` | `{ "status": "ok", "checks": { "db": "ok", "storage": "ok" } }` — 503 if a dependency fails |

## Auth

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/register` | `{ email, password, locale?: "vi"\|"en", ref?: "<referral code>" }` | 201 `User`, sets session cookie, sends verification email |
| POST | `/auth/login-code/request` | `{ email, locale?, ref? }` | 204 always. E-mails a 6-digit code valid 10 min. Unknown e-mails get an account when the code is confirmed |
| POST | `/auth/login-code/verify` | `{ email, code: "123456" }` | 200 `User`, sets session cookie, marks the e-mail verified (grants the signup bonus once). 400 `INVALID_TOKEN` for a wrong/expired code, 429 after 8 tries |
| POST | `/auth/login` | `{ email, password }` | 200 `User`, sets session cookie |
| POST | `/auth/logout` | – | 204, clears cookie |
| POST | `/auth/verify-email` | `{ token }` | 200 `User` (grants the signup bonus once) |
| POST | `/auth/resend-verification` | – (auth) | 204 |
| POST | `/auth/forgot-password` | `{ email }` | 204 always (no account enumeration) |
| POST | `/auth/reset-password` | `{ token, password }` | 204, revokes all sessions |

Passwords: 10–128 characters. Login, register and reset endpoints are rate limited (429 `RATE_LIMITED`).

`User`:
```json
{ "id": "…", "email": "a@b.com", "email_verified": true, "role": "USER", "locale": "vi", "credits": 20, "created_at": "…" }
```
`role` ∈ `USER | ADMIN | SUPER_ADMIN`.

## Me

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/me` | – | `User` (401 if not logged in) |
| PATCH | `/me` | `{ locale? }` | `User` |
| POST | `/me/password` | `{ current_password, new_password }` | 204 (other sessions revoked) |
| DELETE | `/me` | `{ password }` | 202, logs out, schedules deletion of files and personal data |

## Referral

| Method | Path | Response |
|---|---|---|
| GET | `/referral` | `{ code, link, invited, rewarded, reward_credits }`. Both sides get `reward_credits` once, when the invited user's **first payment** succeeds (sign-up alone earns nothing). |

## Public catalogue

| Method | Path | Response |
|---|---|---|
| GET | `/products` | `[ { "code": "starter", "name": "Starter", "credits": 100, "bonus_credits": 30, "price_amount": 49000, "currency": "VND" } ]` (active only, sorted). A purchase grants `credits + bonus_credits`. |
| GET | `/pricing` | `Pricing` |

`Pricing`:
```json
{
  "credits_per_page": { "clean": 1, "overlay": 1 },
  "signup_bonus": 20,
  "languages": { "source": ["Chinese", "Korean", "Japanese", "English"], "target": ["Vietnamese", "English"] },
  "limits": { "max_pages_per_job": 200, "max_upload_mb": 200, "max_concurrent_jobs": 3 },
  "retention_days": 14,
  "credit_megapixels": 2.0,
  "referral_bonus": 50
}
```

## Uploads (direct to object storage)

1. `POST /uploads` `{ filename, size, content_type }` → 201
   ```json
   { "id": "…", "upload_url": "https://…", "method": "PUT", "headers": { "Content-Type": "image/png" }, "expires_in": 900 }
   ```
2. Client `PUT`s the raw bytes to `upload_url` with exactly those headers (the signed URL also pins `Content-Length`).
3. Pass the upload `id`s to `POST /jobs`.

Accepted: `.png .jpg .jpeg .webp` images and `.zip .cbz` archives. Size limits come from `/pricing.limits`. Bytes are validated again (magic bytes, decompression and archive bombs, path traversal) by the worker before processing.

## Jobs

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/jobs` | `CreateJob`, header `Idempotency-Key: <uuid>` (recommended) | 201 `Job` (same key → same job, 200) |
| GET | `/jobs` | – | `{ items: Job[], total }` newest first |
| GET | `/jobs/{id}` | – | `Job` |
| GET | `/jobs/{id}/pages` | – | `PageSummary[]` ordered by `index` |
| POST | `/jobs/{id}/cancel` | – | `Job` |
| POST | `/jobs/{id}/retry` | – | `Job` — re-queues failed pages only |
| DELETE | `/jobs/{id}` | – | 204 — deletes stored files |
| GET | `/jobs/{id}/download?format=zip\|cbz` | – | 200 `{ "status": "ready", "url": "…" }` or 202 `{ "status": "preparing" }` (poll again) |

`CreateJob`:
```json
{
  "title": "Chapter 12",
  "series_id": null,
  "upload_ids": ["…"],
  "source_lang": "Chinese",
  "target_lang": "Vietnamese",
  "mode": "clean",
  "glossary": [ { "source": "师姐", "target": "sư tỷ" } ]
}
```
`mode`: `clean` (remove text + inpaint) or `overlay` (cover text, cheaper and faster).
`series_id` (optional): add the chapter to a series. The series' language pair is used and its glossary + the end of
the previous chapter are given to the translator.
**Page price** = `credits_per_page[mode]` × max(1, ceil(width × height / (`credit_megapixels` × 10⁶))). A normal
1200×1660 page is 1 block; an 800×12000 webtoon strip is 5 blocks. Clients can estimate from image dimensions.
Credits are reserved when the worker knows the page count (after archive extraction); if the balance is too low the job ends `FAILED` with `error.code = "INSUFFICIENT_CREDITS"` and nothing is charged. Only successfully rendered pages are charged; the rest of the reservation is released.

`Job`:
```json
{
  "id": "…", "series_id": null, "title": "Chapter 12", "status": "PROCESSING",
  "source_lang": "Chinese", "target_lang": "Vietnamese", "mode": "clean",
  "page_count": 32, "pages_done": 18, "pages_failed": 0, "pages_review": 1,
  "credits_reserved": 32, "credits_charged": 0,
  "error": null,
  "created_at": "…", "finished_at": null, "expires_at": "…"
}
```
`status` ∈ `PENDING, INGESTING, PROCESSING, TRANSLATING, RENDERING, FINALIZING, COMPLETED, PARTIAL, FAILED, CANCELLED, EXPIRED`.
Terminal: `COMPLETED` (all pages ok), `PARTIAL` (some pages failed, retryable), `FAILED`, `CANCELLED`, `EXPIRED` (files removed by retention).

`PageSummary`:
```json
{
  "id": "…", "index": 0, "status": "ready", "stage": "rendered",
  "needs_review": true, "review_reasons": ["LOW_OCR_CONFIDENCE"],
  "width": 1200, "height": 1660,
  "source_url": "https://signed…", "output_url": "https://signed…",
  "error": null, "updated_at": "…"
}
```
`status` ∈ `pending, processing, ready, failed`; `stage` ∈ `none, prepared, translated, rendered`. Signed URLs expire after ~1 hour.
`review_reasons` ∈ `LOW_OCR_CONFIDENCE, TRANSLATION_UNCERTAIN, TEXT_OVERFLOW, NO_TEXT_FOUND`.

## Series (a.k.a. dictionary / glossary)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/series` | – | `{ items: Series[], total }` most recently updated first |
| POST | `/series` | `{ title, source_lang, target_lang }` | 201 `Series` |
| GET | `/series/{id}` | – | `Series & { glossary: Term[], chapters: Job[] }` (chapters oldest first) |
| PATCH | `/series/{id}` | `{ title?, glossary?: Term[] }` | `Series`. `glossary` replaces the whole list (≤1000 terms, duplicate sources dropped) |
| DELETE | `/series/{id}` | – | 204. Chapters are kept, just ungrouped |

`Series`: `{ id, title, source_lang, target_lang, chapters, terms, created_at, updated_at }`.
`Term`: `{ source, target, auto }`. `auto: true` = learned by the translator from a chapter (shown so the user can
confirm or fix). User terms (`auto: false`) always win over learned ones.

## Sharing and reading

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/jobs/{id}/share` | – | `{ active: false }` or `{ active: true, token_hint, created_at, expires_at, views, url: null }` |
| POST | `/jobs/{id}/share` | `{ days: 1..30 }` | 201 `{ active: true, url: "https://…/s/<token>", … }`. The URL is only returned here; creating a new link revokes the old one. Only finished chapters. |
| DELETE | `/jobs/{id}/share` | – | 204 revoke |
| GET | `/shared/{token}` | – (public, no auth) | `{ title, source_lang, target_lang, expires_at, pages: [ { index, width, height, url } ] }`, or 404 if expired/revoked. The page is a snapshot taken when the link was created. |

The reader for the owner uses `GET /jobs/{id}/pages` (`source_url` + `output_url`) for original/translated comparison.

## Notifications

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/notifications?limit=20` | – | `{ items: [ { id, kind, data, read, created_at } ], unread }` |
| POST | `/notifications/read` | `{ ids: [1,2] }` or `{ all: true }` | 204 |

`kind` + `data`: `job_completed {job_id, title, done, total, status}`, `job_failed {job_id, title, …}`,
`payment_succeeded {credits, amount, currency, payment_id}`, `payment_failed {payment_id}`, `credits_low {balance}`,
`referral_reward {credits}`. The client renders and localizes the text.

## Editor

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/pages/{id}` | – | `PageDetail` |
| PUT | `/pages/{id}/regions` | `{ regions: Region[], version }` | 202 `PageDetail` — re-typesets only (free); 409 `CONFLICT` if `version` is stale |
| POST | `/pages/{id}/regenerate` | `{ what: "translation" \| "inpaint" \| "typeset" }` | 202 `PageDetail` — `translation`/`inpaint` cost credits like one page |

`PageDetail` = `PageSummary` + `{ job_id, clean_url, regions: Region[], version }`. `version` increments on every change; after a 202, poll `GET /pages/{id}` until `version` and `output_url` change.

`Region`:
```json
{
  "id": "r0",
  "bbox": [120, 300, 520, 450],
  "text": "你好，师姐",
  "translation": "Chào sư tỷ",
  "confidence": 0.97,
  "style": { "font_size": null, "alignment": "center", "color": "#000000", "outline": true, "uppercase": false }
}
```
`bbox` is `[x1, y1, x2, y2]` in source-image pixels. `font_size: null` = auto-fit.

## Credits and billing

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/credits` | – | `{ "balance": 120 }` |
| GET | `/credits/transactions` | – | `{ items: [ { id, amount, kind, reason, job_id, created_at } ], total }` |
| POST | `/billing/checkout` | `{ product_code }` | 201 `{ "payment_id": "…", "checkout_url": "https://pay…" }` — redirect the browser there |
| GET | `/billing/payments` | – | `{ items: Payment[], total }` |
| GET | `/billing/payments/{id}` | – | `Payment` (poll on the return page) |
| POST | `/billing/webhooks/{provider}` | provider payload | 200 — called by the payment provider only |

Transaction `kind` ∈ `signup_bonus, purchase, reserve, release, refund, admin_grant, admin_revoke, referral`. A job's net cost is `reserve + release`.
`Payment`: `{ id, product_code, amount, currency, credits, status, created_at, paid_at }`, `status` ∈ `pending, paid, cancelled, failed, refunded`.
Credits are granted only by a verified provider webhook, never by the return URL.

## Admin (`ADMIN` or `SUPER_ADMIN`)

| Method | Path | Body |
|---|---|---|
| GET | `/admin/metrics` | → `{ users, active_users_30d, jobs_by_status, pages_processed, revenue: { VND: 0 }, ai_cost_usd, gross_margin_usd, avg_cost_per_page_usd, avg_processing_seconds, failed_jobs_30d }` |
| GET | `/admin/costs?days=30` | → `[ { date, pages, ai_cost_usd, revenue_vnd } ]` |
| GET | `/admin/users?q=&limit&offset` | → `{ items: AdminUser[], total }` (`AdminUser` = `User` + `status`) |
| GET | `/admin/users/{id}` | → `{ user: AdminUser, jobs: Job[], transactions: [...] }` |
| POST | `/admin/users/{id}/suspend` | `{ reason }` |
| POST | `/admin/users/{id}/restore` | `{ reason }` |
| POST | `/admin/users/{id}/credits` | `{ amount, reason }` (negative = revoke; cannot go below zero) |
| GET | `/admin/jobs?status=&limit&offset` | → `{ items: (Job & { user_email })[], total }` |
| POST | `/admin/jobs/{id}/cancel` \| `/retry` | – |
| POST | `/admin/jobs/{id}/takedown` | `{ reason }`: copyright/abuse removal, cancels and deletes all files (audited) |
| GET | `/admin/payments?status=&limit&offset` | → `{ items: (Payment & { user_email, provider })[], total }` |
| POST | `/admin/payments/{id}/refund` | `{ reason, revoke_credits: true }` — records a refund made through the provider/bank |
| GET | `/admin/providers` | → `[ { id, kind, name, base_url, model, enabled, priority, input_price_per_1m, output_price_per_1m, healthy } ]` |
| PATCH | `/admin/providers/{id}` | `{ enabled?, priority?, model?, input_price_per_1m?, output_price_per_1m? }` |
| GET / PATCH | `/admin/settings` | `{ credits_per_page_clean, credits_per_page_overlay, credit_megapixels, signup_bonus, referral_bonus, credits_low_threshold, usd_vnd_rate, max_pages_per_job, max_concurrent_jobs, retention_days, max_monthly_ai_spend_usd }` |
| GET / POST | `/admin/products` | `{ code, name, credits, bonus_credits, price_amount, currency, active, sort_order }` |
| PATCH | `/admin/products/{id}` | same fields, all optional |
| GET | `/admin/audit?limit&offset` | → `{ items: [ { id, actor_email, action, target_type, target_id, metadata, ip, created_at } ], total }` |

Every admin mutation writes an audit log entry (`ADMIN_SUSPENDED_USER`, `ADMIN_GRANTED_CREDITS`, `ADMIN_CHANGED_PRICE`, …).
