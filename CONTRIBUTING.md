# Contributing

Thanks for your interest in MangaTranslate AI. Bug reports, fixes and features are all welcome.

## Project layout

```
apps/web          Next.js 16 + shadcn/ui (public pages, dashboard, editor, billing, admin)
services/api      FastAPI + SQLAlchemy + Alembic (auth, credits, jobs, payments, admin)
services/worker   queue worker + translation engine (detect → OCR → translate → inpaint → typeset)
infra             Dockerfiles, local compose, production compose + deploy script
docs              architecture, API, billing, security, worker, deployment, operations, DR, licences
```

## Dev setup

Requirements: Docker. No production credentials are needed — MinIO replaces R2, a dev payment provider replaces
payOS, and e-mails are printed in the `worker` logs.

```bash
cp .env.example .env    # optional: add OPENAI_API_KEY / DASHSCOPE_API_KEY for real OCR + translation
docker compose -f infra/compose/docker-compose.yml --env-file .env up --build
```

Without Docker, per service:

```bash
cd services/api && uv venv --python 3.12 && uv pip install -r pyproject.toml --extra dev && .venv/bin/pytest
cd services/worker && uv venv --python 3.12 && uv pip install -r requirements.txt -r ../api/pyproject.toml --extra dev \
  && .venv/bin/python scripts/fetch_models.py && .venv/bin/pytest tests
cd apps/web && pnpm install && pnpm dev
```

Tests use a throwaway embedded Postgres automatically when `DATABASE_URL` is not set.

## Before you open a pull request

Run what CI runs (see [.github/workflows/ci.yml](.github/workflows/ci.yml)):

| Service | Checks |
|---|---|
| `services/api` | `ruff check .` · `pytest -q` · `pip-audit` |
| `services/worker` | `pytest -q tests/test_units.py` (e2e needs models + sample pages) |
| `apps/web` | `pnpm lint` · `pnpm typecheck` · `pnpm build` · `pnpm audit --prod --audit-level high` |

- Keep pull requests small and focused; one logical change per PR.
- Add or update tests for bug fixes and new behaviour.
- Commit messages in the existing style: `type: summary` (`feat:`, `fix:`, `docs:`, `api:`, `worker:`, `web:`).
- Update `docs/` when behaviour, configuration or deployment changes.

## Ground rules

- **Never commit secrets**: real `.env` values, API keys, tokens. `.env.example` documents the variables instead.
- **Never commit copyrighted material**: no scanned manga/manhwa pages. Test images must be openly licensed —
  the repo uses [Pepper&Carrot](https://www.peppercarrot.com) pages by David Revoy (CC-BY 4.0, see
  `samples/CREDITS.txt`).
- Third-party code is vendored only with its licence file and a `NOTICE` entry (see
  [docs/THIRD_PARTY_LICENSES.md](docs/THIRD_PARTY_LICENSES.md) for the audit).
- Security vulnerabilities are reported privately, not as issues — see [SECURITY.md](SECURITY.md).

## Licensing

The project is licensed under the [AGPL-3.0](LICENSE). By contributing you agree that your contributions are
licensed under the AGPL-3.0 as well. There is no CLA; you keep the copyright on your contributions.
