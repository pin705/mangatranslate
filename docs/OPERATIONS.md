# Operations

## Health

| Check | Where |
|---|---|
| API process | `GET /health` |
| API dependencies | `GET /ready` → `{db, storage}`, returns 503 if one fails |
| Workers | `worker_heartbeats` (`last_seen_at` < 1 min per process), container healthcheck on `/tmp/worker-alive` |
| Queue | `/admin/metrics` → `queue_depth`, `dead_tasks` |
| Providers | `/admin/providers` → `healthy` (fewer than 3 consecutive failures), `last_error` |

## Alerts to configure (monitoring stack of your choice on the JSON logs + these queries)

| Alert | Condition |
|---|---|
| API down | `/ready` failing for 2 minutes |
| No worker | no `worker_heartbeats` row newer than 2 minutes |
| Queue backlog | `SELECT count(*) FROM tasks WHERE status='queued' AND run_after < now() - interval '10 minutes'` > 0 |
| Dead tasks | `SELECT count(*) FROM tasks WHERE status='failed' AND updated_at > now() - interval '1 hour'` > 0 |
| Provider failing | `providers.consecutive_failures >= 3` |
| AI spend | month-to-date `sum(provider_usage.cost_usd)` > 80% of `max_monthly_ai_spend_usd` |
| Webhook problems | `payment_events.error` not null in the last hour (`amount mismatch` is critical) |
| Ledger drift | drift query in BILLING.md returns rows |
| Error rate | JSON logs with `level=ERROR` or `status >= 500` above baseline |

## Routine tasks

- **Retry a job**: `/admin/jobs` → Retry (only failed pages; resumes from the last stage).
- **Dead tasks**: inspect `tasks.last_error`. After fixing the cause:
  `UPDATE tasks SET status='queued', attempts=0, run_after=now() WHERE id = …`.
- **Disable a broken provider**: `/admin/providers` → toggle off. Fallback providers take over. Takes effect on
  the next call, no redeploy.
- **Change prices, bonus or limits**: `/admin/system` (audited).
- **Grant or revoke credits**: `/admin/users/{id}` with a reason (audited; cannot go negative).
- **Refund**: pay back through the bank or payOS, then `/admin/payments` → Refund (optionally revokes remaining
  credits).
- **Content takedown (DMCA/abuse)**: `POST /api/v1/admin/jobs/{id}/takedown {reason}` cancels the job and deletes all
  its files (audited). Suspend the user for repeat abuse.

## Data lifecycle

| Data | Deleted by | When |
|---|---|---|
| Raw uploads (`uploads/`) | worker after ingest; bucket rule (1 day) | right after ingest, at most 1 day |
| Sources, cleaned pages, outputs, archive | `system.cleanup` → `job.purge` | `retention_days` (default 14) after the job finishes |
| Everything under `users/` | bucket rule | 60 days (backstop) |
| User-deleted job | `job.purge` | immediately |
| Deleted account | `user.purge` | immediately after the request |
| Sessions, e-mail tokens, rate-limit rows, done tasks | `system.cleanup` | expiry / 1 day / 7 days |
| Payments, payment events, ledger, audit log | kept | accounting / legal retention |

## Capacity notes

Measured on an Apple M1 CPU: detection 1–2.5 s/page, LaMa clean 3–13 s/page, render < 0.3 s. A 30-page chapter is
≈ 3–6 minutes on one CPU worker, plus the remote OCR/translation latency. Add workers (or a GPU worker) to scale.
The first production numbers should replace these.
