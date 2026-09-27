# Security

What is implemented, where, and what is still open. Report vulnerabilities to the security contact in
`/copyright` (placeholder until the legal pages are final).

## Identity and sessions (`mtapi/security.py`, `routers/auth.py`)

- Passwords: argon2id (`argon2-cffi` defaults), 10–128 characters. Unknown e-mails are verified against a dummy
  hash, so login timing does not reveal which accounts exist.
- Sessions: 32-byte random token in an `HttpOnly; SameSite=Lax; Secure` (in production) cookie `mt_session`. Only
  `sha256(token)` is stored. Sliding 30-day expiry. Logout deletes the row.
- Password reset and change revoke other sessions. Reset links last 1 h and verification links 24 h. Tokens are
  single-use and hashed at rest. The one-time link is cleared from the e-mail task payload after sending.
- No tokens in `localStorage`: the web app calls the API same-origin through its proxy.
- Brute force: per-IP and per-e-mail fixed-window limits on login (20/15 min per IP, 10/15 min per account),
  register, forgot/reset password, verification, uploads, job creation, editor saves, checkout.
- Account deletion: password confirmation, immediate anonymisation (e-mail replaced, password removed, sessions
  revoked), then asynchronous deletion of all stored files. Payment and ledger rows stay (accounting), linked to
  the anonymised user.

## Authorization

- Every data route loads the object and checks `user_id` (`own_job`, `own_page`). Another user's IDs return 404,
  not 403, so their existence is not revealed. Tested in `test_jobs.py::test_users_cannot_see_each_other`.
- Admin routes sit behind the `admin_user` dependency at router level. Suspending an admin requires
  `SUPER_ADMIN`, and admins cannot suspend themselves. Every admin mutation writes `audit_logs` (actor, action,
  target, metadata, IP).
- Suspended users are rejected on every request.

## Web-facing protections

- CSRF: unsafe requests with an `Origin` header outside `CORS_ORIGINS` are rejected (`main.guard`), on top of
  `SameSite=Lax`. Payment webhooks are exempt and authenticated by signature instead.
- CORS allowlist from `CORS_ORIGINS`.
- Headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS (production),
  `Cache-Control: no-store` on API responses. The web app (`apps/web/src/proxy.ts`) sends a per-request nonce CSP:
  `script-src 'nonce-…' 'strict-dynamic'`, no inline scripts, `frame-ancestors 'none'`, `form-action 'self'`, and
  images/uploads limited to the storage origin (`CSP_STORAGE_ORIGIN`). `style-src` allows inline styles, which UI
  positioning needs; styles cannot execute code. Verified in headless Chrome: no violations across the app.
- Errors: a consistent JSON shape. Unhandled exceptions return a generic message; stack traces are only logged.
- OpenAPI docs are disabled in production.
- SQL: SQLAlchemy only (parameterised), with a handful of static `text()` queries and bound parameters.
- SSRF: the server never fetches user-supplied URLs. Outbound calls go only to configured provider base URLs
  (admin-editable, so admin accounts are sensitive) and to our own bucket.

## Uploads (`routers/jobs.py`, `worker/ingest.py`)

Extension allowlist + server-chosen `Content-Type` + a size limit signed into the upload URL. The worker then
checks magic bytes, reads archives in memory (entry names never touch disk), rejects absolute paths, `..`,
encrypted entries, per-entry size above 60 MB, compression ratio above 100 and totals above 1 GB, fully decodes
every image under a pixel cap (40 MP) and enforces the page cap. Filenames are sanitised before they are used in
object keys. Tested in `worker/tests/test_units.py`.

## Secrets

Only environment variables, never in git (`.env` ignored, `.env.example` documents them). Provider rows store the
*name* of the key variable, not the key. `Settings.check()` refuses to start production with the default
`AUTH_SECRET`, the dev payment provider, console e-mail or a non-HTTPS `WEB_URL`. Logs never include request
bodies, tokens, keys or images.

## Money

See BILLING.md: signed and idempotent webhooks, ledger with a row lock and `CHECK (balance >= 0)`, no credit from
the client side.

## Dependency hygiene

CI runs `pip-audit` (API) and `pnpm audit --prod` (web) on every PR. AGPL `ultralytics` was removed from the
runtime. Licences are in THIRD_PARTY_LICENSES.md.

## Open items before launch

- [ ] External security review / penetration test.
- [ ] Firewall the origin to Cloudflare IP ranges (rate limiting trusts `CF-Connecting-IP`).
- [ ] Turn on Cloudflare WAF managed rules and bot protection for `/api/v1/auth/*`.
- [ ] Error tracking (Sentry or similar) wired to the JSON logs. Not added yet.
- [ ] Abuse heuristics beyond rate limits (repeated failed payments, account farming by device/IP), and
      progressive limits instead of fixed windows.
- [ ] Google OAuth (optional in the spec). Not implemented.
