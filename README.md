# MangaTranslate AI

Upload manga / manhwa / manhua pages and get clean translated pages back (Chinese, Korean, Japanese → Vietnamese,
English). The web app lets users upload a chapter, follow its progress, fix any page in a browser editor and
download the result as ZIP or CBZ. Credits are bought with VietQR (payOS).

```
apps/web          Next.js 16 + shadcn/ui (public pages, dashboard, editor, billing, admin)
services/api      FastAPI + SQLAlchemy + Alembic (auth, credits, jobs, payments, admin)
services/worker   queue worker + translation engine (detect → OCR → translate → inpaint → typeset)
infra             Dockerfiles, local compose, production compose + deploy script
docs              architecture, API, billing, security, worker, deployment, operations, DR, licences
```

## Run locally

Requirements: Docker. No production credentials are needed: MinIO replaces R2, a dev payment provider replaces
payOS, and e-mails (with verification links) are printed in the `worker` logs.

```bash
cp .env.example .env    # optional: add OPENAI_API_KEY / DASHSCOPE_API_KEY for real OCR + translation
docker compose -f infra/compose/docker-compose.yml --env-file .env up --build
```

Web http://localhost:3000 · API docs http://localhost:8000/api/docs · MinIO http://localhost:9001 (minioadmin / minioadmin).
The local worker uses the model-free text mask unless you build it with `SEGMENTER_ONNX_URL` (see docs/MODEL_LICENSES.md).
Make yourself admin: `docker compose … exec postgres psql -U postgres mangatranslate -c "UPDATE users SET role='SUPER_ADMIN' WHERE email='you@…'"`.

Without Docker, per service:

```bash
cd services/api && uv venv --python 3.12 && uv pip install -r pyproject.toml --extra dev && .venv/bin/pytest
cd services/worker && uv venv --python 3.12 && uv pip install -r requirements.txt -r ../api/pyproject.toml --extra dev \
  && .venv/bin/python scripts/fetch_models.py && .venv/bin/pytest tests
cd apps/web && pnpm install && pnpm dev
```

Tests use a throwaway embedded Postgres automatically when `DATABASE_URL` is not set.

## Try translation quality on real pages

```bash
cd services/worker && scripts/try_samples.sh          # uses OPENAI_API_KEY / OPENAI_BASE_URL
```

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Billing](docs/BILLING.md) · [Worker](docs/WORKER.md) ·
[Security](docs/SECURITY.md) · [Deployment](docs/DEPLOYMENT.md) · [Operations](docs/OPERATIONS.md) ·
[Disaster recovery](docs/DISASTER_RECOVERY.md) · [Third-party licences](docs/THIRD_PARTY_LICENSES.md) ·
[Models](docs/MODEL_LICENSES.md) · [Status and launch plan](docs/IMPLEMENTATION_PLAN.md)

## Licence

Proprietary. `services/worker` contains Apache-2.0 code from luxivint/ai-manga-translator and ogkalu2/comic-translate
(see `services/worker/LICENSE` and `NOTICE`).
