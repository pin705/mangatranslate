# Implementation status and launch plan

Status as of 2026-09-27, measured against `AI_Manga_Translator_SaaS_PRODUCTION_SPEC.md`. "Verified" means covered by
an automated test or a recorded run. Everything else is marked for what it is.

## Decisions that differ from the spec (and why)

| Spec | Built | Why |
|---|---|---|
| SvelteKit frontend | Next.js 16 + shadcn/ui | Product owner's choice (speed of UI work). SSR/SEO and the same-origin API proxy are unchanged. |
| Redis + Celery/Dramatiq/RQ | Postgres task queue | Enqueueing is atomic with state changes and there is one less system to run. It meets every listed queue requirement (retry, delayed retry, dead letter, visibility, cancellation, idempotency, concurrency). See ARCHITECTURE.md. |
| Redis rate limiting | Postgres fixed-window + Cloudflare in front | Same call site (`rate_limit()`), swap when volume demands it. |
| Separate GPU worker from day one | One worker image. GPU = build arg + `MODEL_QUEUE=gpu` | CPU is enough to launch (5–15 s/page measured). The split is configuration, not a code change. |
| Subscriptions | Credit packs only | VietQR has no recurring charge. Subscriptions ship with a card/MoR provider. |
| ultralytics YOLO runtime | ONNX Runtime | AGPL-3.0. See THIRD_PARTY_LICENSES.md. |

## Phases

| Phase | Status |
|---|---|
| 1 Foundation: monorepo, Docker, Postgres, migrations, auth, storage, API, web, CI | **Done**. Docker images and compose are written but **not built on this machine** (Docker daemon unavailable); CI builds them. |
| 2 Translation engine | **Done**, CJK sources fixed. Real models verified locally (detection, segmentation, inpainting, typesetting). **Real OCR + translation quality not measured yet** (provider API unreachable from the build sandbox). Run `scripts/try_samples.sh`. |
| 3 Production job system | **Done and verified**: state machine, fan-out/fan-in, retries, leases, idempotent stages, cancel, progress, per-page failure isolation. |
| 4 Editor | **Done and verified in headless Chrome**: edit text, move/resize, style, undo/redo, zoom/pan, shortcuts, save → re-typeset, regenerate. Not built: adding or deleting regions. |
| 5 Billing | **Done**: products, ledger, reservations, payOS checkout + webhooks + reconciliation, refunds, history. Not built: subscriptions, credit expiry. **payOS not exercised against the real service yet.** |
| 6 Admin | **Done**: metrics, costs, users, credits, jobs, payments/refunds, providers, settings/products, audit, takedown. |
| 7 Hardening | Partly done: security headers + CSP, rate limits, upload/archive defences, cleanup jobs, health/readiness, JSON logs, backups documented. **Not done**: error tracking (Sentry), alert wiring, load test, restore test, abuse heuristics beyond rate limits. |
| 8 Public launch | Checklist below. |

## Verified so far

- `services/api/tests`: 29 tests on real Postgres (ledger concurrency with 25 threads, idempotency, webhooks incl.
  replay/bad signature/amount mismatch, authz isolation, auth flows, rate limit, CSRF, job billing incl.
  partial/retry/cancel, admin audit, header-safe downloads).
- `services/worker/tests`: 11 tests (translation validation, malicious uploads, full chapter e2e with real models).
- Local full-stack run (Next.js → FastAPI → Postgres → S3 → worker), 18 HTTP smoke checks and 12 headless-Chrome
  checks. This found and fixed two real bugs: a Vietnamese download filename broke the download header, and editor
  re-renders were invisible. The only stub was the remote OCR/translation, because the sandbox blocks the
  provider.

## Launch checklist (spec §85 Phase 8)

| Item | Status | How |
|---|---|---|
| Go/no-go translation quality on real chapters (zh/ko/ja → vi/en) | ☐ **blocking** | `scripts/try_samples.sh` with your key, on your own pages |
| Payment test | ☐ | staging payOS, smallest pack, real transfer |
| Webhook idempotency test | ✅ automated | `test_billing.py` |
| Credit concurrency test | ✅ automated | `test_ledger.py` |
| Restore backup test | ☐ **blocking** | DISASTER_RECOVERY.md; fill in the table |
| Job retry test | ✅ automated | `test_jobs.py::test_pipeline_fan_out_fan_in_and_billing` |
| Worker crash test | ☐ | kill a worker mid-page in staging; the task is re-claimed after the lease (10 min) |
| Storage cleanup test | ☐ | set `retention_days=0` in staging, run cleanup, check the bucket |
| Account deletion test | ✅ API, ☐ storage | `test_auth.py`; verify files disappear in staging |
| Security review | ☐ | external pentest; SECURITY.md open items |
| Licence review | ☐ **blocking** | counsel on the MODEL_LICENSES.md "review" rows (segmenter weights, dataset provenance) |
| Legal pages | ☐ **blocking** | Terms, Privacy (disclose AI processors), copyright/DMCA contact, reviewed for Vietnam |
| Production smoke test | ☐ | DEPLOYMENT.md |

## Next work, in order

1. Quality go/no-go with real providers. Tune `SEG_CONF`, font sizes and the translation prompt on real chapters.
2. Staging on a VM: build images, payOS test merchant, R2 bucket with lifecycle + CORS, SMTP.
3. Sentry (API, worker, web) and the alert queries in OPERATIONS.md.
4. Restore test, worker-crash test, cleanup test (checklist).
5. Legal review, then public launch in Vietnam (VietQR).
6. After launch: local OCR (manga-ocr / PP-OCR) to cut cost, a merchant-of-record provider for international cards
   and subscriptions, region add/delete in the editor, remove the dead ad/stamp code from the vendored CLI.
