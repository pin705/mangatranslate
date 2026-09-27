# Disaster recovery

## What matters

| Data | Source of truth | Loss impact |
|---|---|---|
| PostgreSQL (users, ledger, payments, jobs, audit) | managed Postgres | **critical** (money and accounts) |
| R2 objects (pages and outputs) | R2 | medium: temporary by design (14-day retention). Users can re-upload. |
| Secrets (`.env`) | secret manager / password vault | high: keep an offline copy |
| Images | GHCR, rebuilt from git | low |

## Backups

- Use a managed Postgres with **automated daily backups + point-in-time recovery**, retention ≥ 14 days (Neon,
  Supabase, DigitalOcean, RDS, Cloud SQL all offer this).
- Plus a weekly logical dump to a different provider or region (encrypted):
  `pg_dump --format=custom --no-owner "$DATABASE_URL" | age -r <pubkey> > mt-$(date +%F).dump.age`,
  keeping 8 weekly copies.
- R2: no backups (retention is short by design). Enable bucket versioning only if you decide outputs must be
  recoverable.

## Restore procedure

1. Pick the target time (before the incident). Freeze writes: scale workers to 0 and put the API behind a
   maintenance page (or stop it).
2. Managed PITR: restore into a **new** instance at the target time. From a dump:
   `createdb mt_restore && age -d dump.age | pg_restore --no-owner -d mt_restore`.
3. Check the restore: `alembic current` equals the expected revision; row counts for users, payments and
   credit_transactions; the ledger drift query in BILLING.md returns nothing.
4. Reconcile payments made after the restore point: list the provider's paid orders since then
   (payOS dashboard) and replay them. `handle_event` is idempotent, so replaying known events is safe.
5. Point `DATABASE_URL` at the restored instance and redeploy the matching image tag.
6. Resume workers. Interrupted tasks resume from their stored stage.

## Periodic restore test (required before launch, then quarterly)

Restore the latest backup into a scratch instance, run step 3, run `services/api` tests against it
(`DATABASE_URL=… pytest`, on a copy only), and record the date, duration and any problems in the table below.

| Date | Backup used | Time to restore | Result | Notes |
|---|---|---|---|---|
| — | — | — | not yet tested | Launch is blocked until this row is filled |

## Targets

RPO ≤ 5 minutes (PITR), RTO ≤ 2 hours for the database. These only hold once the test above has been run.
