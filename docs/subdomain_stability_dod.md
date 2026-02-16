# Subdomain Stability DoD

## Common Definition of Done
- `/` landing page (or redirect to `/docs`).
- `/health` returns `200` JSON.
- CORS enabled for `/health` for status-board polling.
- Legacy redirects kept (ex: `/wallet` -> `https://thronoschain.org/downloads/`).

## Railway (Flask)
- Services: `api.thronoschain.org`, `ro.api.thronoschain.org`, `verifyid-api.thronoschain.org`, `btc-api.thronoschain.org`.
- Healthcheck path in Railway: `/health`.
- App must listen on runtime `PORT`.

## Render (FastAPI)
- Services: `ai.thronoschain.org`, `sentinel.thronoschain.org`.
- Keep `/` landing and `/health` JSON.
- Set Render healthcheck path to `/health`.

## Vercel (VerifyID / Explorer)
- Services: `verifyid.thronoschain.org`, `explorer.thronoschain.org`.
- Provide `public/health.json` (or `/api/health`) so status probe marks UP.

## Backbone: Token Registry + Event Bus
- `data/tokens_registry.json` keeps token decimals/chain/rpc env/treasury.
- Event types: `MUSIC_TIP`, `PLAY_BATCH_ROOT`, `TELEMETRY_ROOT`, `BRIDGE_DEPOSIT`, `SETTLED`.
- Use decimal-safe amounts and async settlement (`PENDING` -> `SETTLED`).

## Node2 Treasury
- Keep treasury on Node2 with separate keys.
- Required endpoints: `/treasury/health`, `/treasury/balances`.
- Worker must detect deposits/confirmations and settle payouts.

## X9 Gateway hardening
- Origin allowlist.
- Rate limiting.
- Short-lived signed envelopes.
- HMAC (`timestamp + nonce + body`) validation.
- Log metadata only (never secrets/raw payloads).
