# Deployment

## Environments

| | local | staging | production |
|---|---|---|---|
| How | `docker compose -f infra/compose/docker-compose.yml up --build` | `release.yml` auto-deploys every green `main` | `release.yml` → "Run workflow" with `deploy_production`, approved in the GitHub `production` environment |
| Database | compose Postgres | own managed Postgres | own managed Postgres with PITR |
| Storage | MinIO | own R2 bucket | own R2 bucket |
| Payments | `dev` provider | payOS test merchant (small real amounts) | payOS live |
| AI keys | yours (optional) | separate keys with low budgets | production keys |

Never reuse production credentials in local or staging.

## Server requirements (single VM to start)

- Linux x86-64, Docker Engine + Compose v2. 4 vCPU / 8 GB RAM covers web + api + 1–2 CPU workers (≈2.5 GB each).
- Optional GPU host for `worker-gpu`: NVIDIA driver ≥ 550 and the NVIDIA Container Toolkit. CUDA/cuDNN come
  inside the image (pip wheels).
- Outbound HTTPS to R2, the managed Postgres, AI providers, payOS and SMTP.

## First-time setup

1. **DNS / Cloudflare**: proxied record for `DOMAIN`, SSL mode "Full (strict)". Firewall 80/443 on the VM to
   [Cloudflare IP ranges](https://www.cloudflare.com/ips/).
2. **Postgres**: create a managed instance with automated backups + point-in-time recovery (see
   DISASTER_RECOVERY.md). Put its URL in `DATABASE_URL` with `sslmode=require`.
3. **R2**: create a bucket per environment and an API token scoped to that bucket. Add lifecycle rules:
   `uploads/` expire after 1 day, `users/` expire after 60 days (backstop). Add a CORS rule allowing `PUT, GET`
   from `https://DOMAIN` (browsers upload directly).
4. **Segmenter model**: run `services/worker/scripts/export_segmenter.py` once, upload the ONNX file to a private
   bucket URL, and set the repository secret `SEGMENTER_ONNX_URL` (or build with `SEGMENTER=none`).
5. **payOS**: create a payment channel, set the webhook URL `https://DOMAIN/api/v1/billing/webhooks/payos`, and
   copy the client ID, API key and checksum key into `.env`.
6. **SMTP**: any relay. Set up SPF, DKIM and DMARC for the sending domain.
7. **VM**: create user `deploy`, copy `infra/deploy/*` to `/srv/mangatranslate/`, create `.env` from
   `.env.example` (`AUTH_SECRET=$(openssl rand -hex 32)`), and `docker login ghcr.io`.
8. **GitHub**: environments `staging` and `production` (add required reviewers to production) with secrets
   `DEPLOY_SSH_KEY`, `DEPLOY_HOST`; repository secret `SEGMENTER_ONNX_URL`.
9. First deploy: `TAG=<sha> ./deploy.sh`, then create the first admin:
   ```sql
   UPDATE users SET role = 'SUPER_ADMIN' WHERE email = 'you@example.com';
   ```
10. Smoke test (below).

## Each release

`deploy.sh`: pull images → `alembic upgrade head` (one-shot `migrate` service) → `up -d` → wait for `/ready` →
record the tag. Workers get a 10-minute stop grace period so the current page finishes. Tasks that do get
interrupted are re-claimed after their lease expires.

**Migrations are forward-only and must be backward compatible with the previous release** (expand → deploy →
contract in a later release). Destructive schema changes ship with a tested restore plan (DISASTER_RECOVERY.md).

## Rollback

`TAG=$(cat .previous_tag) ./deploy.sh`. Thanks to the rule above, the older API/worker/web run against the newer
schema. If a migration itself was wrong, restore to a point in time (DISASTER_RECOVERY.md) and redeploy the
previous tag.

## Scaling

- More CPU workers: `docker compose -f docker-compose.prod.yml up -d --scale worker=N` (claiming uses `SKIP LOCKED`).
- GPU: `MODEL_QUEUE=gpu` in `.env` for both api and workers, `--profile gpu up -d worker-gpu`. CPU workers keep
  ingest/translate/finalize/e-mail.
- Web/API are stateless: run more replicas behind Caddy, or move them to separate hosts.

## Smoke test (every production deploy)

1. `curl https://DOMAIN/ready` returns `db: ok, storage: ok`.
2. Register → verification e-mail → verify → 20 credits.
3. Upload a 2-page CBZ → job completes → preview → download ZIP and CBZ.
4. Edit one bubble in the editor → the output updates and no credits are charged.
5. Staging only: buy the smallest pack with payOS → credits appear → the receipt e-mail arrives.
6. `/admin` metrics show the job, pages, AI cost and payment.
