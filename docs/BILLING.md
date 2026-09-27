# Billing and credits

## Model

- **Price per page = rate × blocks.** `rate` = `credits_per_page_{clean|overlay}` (default 1, snapshotted on the
  job at creation). `blocks` = max(1, ceil(width × height / (`credit_megapixels` × 10⁶))), default 2 MP per block.
  A normal 1200×1660 page is 1 block. An 800×12000 webtoon strip is 5 blocks, so long strips pay for the compute
  they use. The price is stored per page (`pages.credits`) at ingest.
- **Credit packs** (`products` table: code, name, credits, price in VND) are managed in `/admin/system`. The
  seeded prices (Starter 100 = 49,000 VND, Pro 500 = 199,000 VND, Power 2000 = 699,000 VND) are placeholders.
- **Signup bonus** (`signup_bonus`, default 20) is granted when the e-mail is **verified** (link or login code), not
  at registration, which makes account farming harder.
- **Pack bonus** (`products.bonus_credits`): promotional extra credits granted with the pack and snapshotted on the
  payment.
- **Referrals**: `referral_bonus` (default 50) for both users, granted once, when the invited user's **first
  payment** succeeds (ledger kind `referral`, keys `referral:referrer:{invitee}` and `referral:referee:{invitee}`).
  Sign-ups alone earn nothing, so farming accounts is pointless.
- Subscriptions are not offered yet (VietQR has no recurring charge). See ARCHITECTURE.md → limits.
- Credits do not expire. Adding expiry would mean a scheduled `expire` transaction kind.

## Ledger

`credit_transactions` is append-only: every change is a row (`signup_bonus, purchase, reserve, release, refund,
admin_grant, admin_revoke`). The balance is the sum of the rows. `credit_wallets.balance` is a cache, updated in
the same transaction under `SELECT … FOR UPDATE` on the wallet row, and a `CHECK (balance >= 0)` constraint makes
overdraft impossible even if code is wrong. `ledger.apply` is the only writer. An `idempotency_key` (unique) turns
repeated calls into no-ops.

Reconciliation: `ledger.ledger_sum(user)` must equal the wallet balance. The admin user detail shows both.

```sql
-- drift check (should return no rows)
SELECT w.user_id, w.balance, coalesce(sum(t.amount), 0) AS ledger
FROM credit_wallets w LEFT JOIN credit_transactions t ON t.user_id = w.user_id
GROUP BY w.user_id, w.balance HAVING w.balance <> coalesce(sum(t.amount), 0);
```

## Job lifecycle

```
ingest: page sizes known ─► reserve Σ page prices     (reserve:{job}:{generation})
finalize / cancel         ─► charge rendered, unbilled pages; release the rest   (release:{job}:{generation})
retry failed pages        ─► generation + 1, reserve Σ failed page prices, same settlement
regenerate one page       ─► reserve that page's price (regen:{page}:{version}); kept on success, released on final failure
typeset-only edits        ─► free
```

Insufficient balance at ingest ends the job `FAILED / INSUFFICIENT_CREDITS` with nothing charged. The user buys
credits and presses Retry. `pages.billed` makes sure a page is charged at most once.

## Payments

`payments.base.PaymentProvider`: `create_checkout`, `parse_webhook` (verifies the signature), `fetch_status`
(server-to-server status, used to reconcile missed webhooks), `refund`.

| Provider | Use | Notes |
|---|---|---|
| `payos` | Production (Vietnam, VietQR bank transfer) | HMAC-SHA256 signatures exactly as in the official SDK. Configure the webhook URL `https://<domain>/api/v1/billing/webhooks/payos` in the payOS dashboard. No refund API: refunds are bank transfers, recorded in admin. |
| `dev` | Local / test only | Checkout page with "simulate paid / cancelled" buttons that produce a signed webhook through the normal processing path. The API refuses to start with it when `APP_ENV=production`. |

Flow: `POST /billing/checkout` creates a `pending` payment with a random 13-digit `order_code` and redirects to
the provider. The provider calls the webhook. `billing.handle_event`:

1. inserts the event into `payment_events` with unique `(provider, event_id)`. A duplicate delivery or replay is
   a no-op;
2. locks the payment row;
3. checks the amount matches;
4. marks it paid and applies `+credits` with idempotency key `purchase:{payment_id}`;
5. enqueues the receipt e-mail.

All of this happens in one DB transaction. **The return URL grants nothing.** The return page polls
`GET /billing/payments/{id}`, which may ask the provider for the status (at most every 10 s) and then runs the
same `handle_event`.

Refund (admin): marks the payment `refunded` and optionally revokes up to the credits still available (never
below zero). The shortfall is recorded in the audit log. Chargebacks do not exist for VietQR transfers. A card or
MoR provider would map its dispute events to the same refund path.

## Margin

`provider_usage.cost_usd` (per OCR/translation call, from provider prices in the `providers` table) against paid
payments. `/admin/metrics` shows revenue, AI cost, gross margin (VND converted with the `usd_vnd_rate` setting) and
average cost per page. `/admin/costs` shows daily pages, AI cost and revenue. Payment-provider fees and storage cost
are not captured automatically. Take them from the provider statements.

## Pre-launch money checks

Automated (`services/api/tests`): concurrent reservations cannot overspend (25 threads), idempotent ledger keys,
duplicate/replayed/unsigned/wrong-amount webhooks, the frontend cannot fake success, unverified users cannot buy,
refund revokes and audits, job settlement including partial failure, retry and cancel.
Manual before real money: one real payOS payment and webhook in staging with a small amount; confirm the receipt
e-mail; run the drift query.
