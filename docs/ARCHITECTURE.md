# Architecture

```
Browser ──► Cloudflare ──► Caddy (TLS) ─┬─► web  (Next.js, SSR pages + app UI)      ── server-side calls ──┐
                                        └─► api  (FastAPI, /api/v1, /health, /ready) ◄──────────────────────┘
                                               │ enqueue tasks in the same transaction as state changes
            signed PUT/GET URLs                ▼
Browser ◄────────────────────────► R2    PostgreSQL ◄── claim (FOR UPDATE SKIP LOCKED) ── workers (N×, CPU / GPU)
                                   ▲                                                       │
                                   └─────────────── page images, masks, outputs ◄──────────┘
                                                               │ OCR + translation (OpenAI-compatible APIs)
                                                               ▼
                                                        AI providers (fallback, budget cap)
```

Five things run: **web, api, worker(s), Postgres, object storage**. There is no Redis, broker or separate
scheduler: the queue is a Postgres table (see "Queue" below). Each component scales on its own. Web and API are
stateless, and workers are added by running more containers.

## Code map

| Path | What |
|---|---|
| `apps/web` | Next.js + shadcn/ui. Public SEO pages, dashboard, jobs, editor, billing, settings, admin. i18n vi/en. It calls the API same-origin (`/api/*` is proxied), so the session cookie stays HttpOnly. |
| `services/api/mtapi` | FastAPI service, split by domain: `security` (identity, sessions, rate limits), `ledger` (credits), `billing` + `payments/` (payment providers), `jobs` (state machine + orchestration), `queue`, `storage`, `emails`, `app_settings` (pricing, limits, audit), `routers/` (HTTP only). |
| `services/api/migrations` | Alembic, forward-only. |
| `services/worker` | `runner.py` (queue consumer), `tasks.py` (one handler per task kind), `pipeline.py` (engine adapter), `ai.py` (providers, fallback, cost, translation validation), `ingest.py` (untrusted upload handling). `modules/`, `app/`, `imkit/`, `scripts/local_batch.py` are the vendored engine (Apache-2.0). |
| `infra/` | Dockerfiles, local compose, production compose + Caddy + deploy script. |

The worker imports `mtapi` (models, ledger, queue, storage) so there is one schema and one set of money rules.
The API never imports the worker, so API images carry no ML dependencies.

## Processing pipeline

A chapter is a **job**. Its pages move through stages, and each arrow below is a queued task:

```
job.ingest ─► page.prepare ×N ─► job.translate ─► page.render ×N ─► job.finalize
 validate,     detect, OCR,       one batched call     typeset onto      settle credits,
 extract,      clean/inpaint,     for the chapter      cleaned image     notify
 reserve       store regions      (context + glossary)
 credits
```

- `jobs.advance(job)` is the only place that decides what runs next. It runs under the job row lock after every
  stage, looks at page stages and enqueues the next tasks with **dedupe keys** (`prepare:{page}:{generation}` …),
  so calling it twice never duplicates work.
- Pages keep their last completed stage (`none → prepared → translated → rendered`). A retry bumps
  `job.generation` and resumes failed pages from their stage. OCR and inpainting are not paid for twice.
- Job states: `PENDING, INGESTING, PROCESSING, TRANSLATING, RENDERING, FINALIZING, COMPLETED, PARTIAL, FAILED,
  CANCELLED, EXPIRED`. Allowed transitions are in `jobs.TRANSITIONS`, and anything else raises.
- A failed page does not fail the chapter: the job ends `PARTIAL`, only rendered pages are charged, and "Retry"
  re-queues just the failed pages.
- Editor: `regions` (bbox, OCR text, translation, style) live on the page row. Saving enqueues `page.typeset`,
  which re-renders from the stored cleaned image with no AI calls and no charge. "Regenerate translation /
  inpaint" re-runs only that stage and costs one page of credits.

## Queue

`tasks` table + `mtapi/queue.py`: priorities, `run_after` for delayed retries with exponential backoff (30 s, 2 m,
8 m), `max_attempts` then `status=failed` (dead letter, visible in admin metrics), 10-minute leases renewed by a
thread while a task runs (a crashed worker's tasks are re-claimed after the lease), cancellation (`queued →
cancelled`), per-queue routing (`default` for CPU, `gpu` for model work when `MODEL_QUEUE=gpu`) and dedupe keys for
idempotent enqueueing. Enqueueing happens in the same DB transaction as the state change that causes it, so there
are no lost or phantom tasks.

Why not Redis + Celery: it would be a second source of truth and give up that atomicity, and at our volume it
buys nothing. Revisit if claiming latency or throughput (thousands of tasks per minute) becomes a problem.

## AI providers

`providers` table (kind, base URL, model, priority, enabled, prices, env var **name** of the key). Workers try
providers in priority order and fall back on errors. After 5 consecutive failures a provider is skipped (circuit
breaker) unless it is the only one. Every call writes `provider_usage` (tokens, duration, cost, success,
`uncertain` for timeouts that may still have been billed). A monthly spend cap (`max_monthly_ai_spend_usd`) stops
calls before the budget is exceeded. Admins can disable a provider or change models and prices without a
redeploy. All providers speak the OpenAI-compatible chat API. A vendor with a different API needs one branch in
`ai._chat`.

Translation is one batched request per chapter (≤120 lines per call) with the glossary and the last 15
translated lines as context. The reply must be JSON; `ai.validate` rejects missing or untranslated lines and
malformed Unicode, and flags lost placeholders or suspiciously long lines. Rejected lines are retried, then sent
to the next provider. Anything still doubtful marks the page `needs_review`.

## Storage

See `mtapi/storage.py` for the key layout. Browsers upload and download directly with short-lived signed URLs;
the API never proxies image bytes. Uploads live under `uploads/` (bucket rule: expire after 1 day). Job data lives
under `users/{id}/jobs/{id}/`: the app deletes it when the job expires, and a bucket rule is the backstop.

## Deliberate limits (with upgrade paths)

| Limit | Upgrade when |
|---|---|
| Queue in Postgres | Sustained thousands of tasks/min: move to a broker, keep the `tasks` table as the ledger |
| Rate limits in Postgres (fixed window) | Request volume makes the table hot: move to Redis, same `rate_limit()` call |
| One payment rail (payOS) + dev provider | International customers: add a merchant-of-record provider implementing `payments.base.PaymentProvider` |
| Credit packs only (no subscriptions) | VietQR has no recurring charge. Add subscriptions together with a card/MoR provider |
| Vision-LLM OCR only | Local OCR (manga-ocr / PP-OCR) once quality has been measured, to cut cost and keep images in-house |
| Chapter archive rebuilt in memory | Chapters beyond a few hundred MB: stream the ZIP to storage |
