# MangaTranslate AI — web

Next.js 16 (App Router) frontend. Talks to the FastAPI backend strictly per `docs/API.md`.

## Environment

| Variable | Default | Used for |
| --- | --- | --- |
| `API_URL` | `http://localhost:8000` | Base URL of the API. The browser calls `/api/*` same-origin and Next rewrites it here (**resolved at build time**); server components also call it directly at runtime, forwarding the session cookie. |
| `NEXT_PUBLIC_SITE_URL` | `http://localhost:3000` | Canonical/OpenGraph URLs, `sitemap.xml`, `robots.txt` (**build time**). |

Locale comes from the `NEXT_LOCALE` cookie (`vi` default, or `en`); messages live in `messages/{vi,en}.json`.

## Commands

```bash
pnpm install
pnpm dev            # http://localhost:3000 (API expected on :8000)
pnpm lint
pnpm typecheck      # next typegen && tsc --noEmit
pnpm test           # node --test: glossary/upload rules + vi/en message key parity
pnpm build          # standalone output in .next/standalone
```

## Docker

```bash
docker build -t mangatranslate-web \
  --build-arg API_URL=http://api:8000 \
  --build-arg NEXT_PUBLIC_SITE_URL=https://example.com .
docker run -p 3000:3000 -e API_URL=http://api:8000 mangatranslate-web
```

Direct uploads `PUT` to the signed object-storage URL from the browser, so the bucket needs CORS allowing `PUT` from the site origin.
