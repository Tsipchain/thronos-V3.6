# Thronos Subdomain Health Runbook (Q2 2026 Baseline)

## 1) Domain → service mapping

| Domain | Platform | Service | Health URL (canonical) | Fallback(s) |
|---|---|---|---|---|
| `api.thronoschain.org` | Railway (Flask) | Primary API | `https://api.thronoschain.org/health` | `/api/health` |
| `ro.api.thronoschain.org` | Railway (Flask) | Read-only API | `https://ro.api.thronoschain.org/health` | `/api/health` |
| `verifyid-api.thronoschain.org` | Railway (Flask) | VerifyID API | `https://verifyid-api.thronoschain.org/health` | none |
| `btc-api.thronoschain.org` | Railway (Flask) | BTC Adapter API | `https://btc-api.thronoschain.org/health` | `/api/health` |
| `ai.thronoschain.org` | Render (FastAPI/Flask edge) | AI Core | `https://ai.thronoschain.org/health` | `/api/health` |
| `sentinel.thronoschain.org` | Render (FastAPI) | Sentinel | `https://sentinel.thronoschain.org/health` | `/api/health` |
| `verifyid.thronoschain.org` | Vercel (frontend) | VerifyID UI | `https://verifyid.thronoschain.org/health.json` | `/health` |
| `explorer.thronoschain.org` | Vercel (frontend) | Explorer UI | `https://explorer.thronoschain.org/health.json` | `/api/health` |

---

## 2) Health endpoint contract

Dynamic services (`/health`):

```json
{
  "ok": true,
  "service": "<service-name>",
  "role": "<node-role>",
  "version": "<app-version>",
  "ts": 1710000000
}
```

Requirements:
- Methods: `GET`, `OPTIONS`
- CORS headers:
  - `Access-Control-Allow-Origin: *`
  - `Access-Control-Allow-Methods: GET,OPTIONS`
  - `Access-Control-Allow-Headers: Content-Type,Authorization`

Static services:
- Provide `/health.json` with at least `{ "ok": true, "service": "...", "ts": ... }`.

---

## 3) Deployment checklist

### Railway (api / ro.api / verifyid-api / btc-api)
1. Service is bound to `0.0.0.0:$PORT`.
2. `Healthcheck Path` set to `/health`.
3. Custom domain attached and SSL certificate issued.
4. Env vars include any host allowlists (if enforced):
   - e.g. `ALLOWED_HOSTS`, `X9_ALLOWED_ORIGINS`.

### Render (ai / sentinel)
1. Custom domains attached (`ai`, `sentinel`).
2. Health Check Path set to `/health`.
3. Any CORS allowlist includes status board origin(s).
4. SSL cert status = issued.

### Vercel (verifyid / explorer)
1. Add `public/health.json` to deployed artifact.
2. Custom domain attached and certificate valid.
3. If rewrites are used, ensure `/health.json` bypasses app routing.

---

## 4) Smoke test

Run from repo root:

```bash
python3 scripts/smoke_subdomains_health.py --timeout 20 --retries 3
```

Expected:
- `summary.failed == 0`
- every target returns JSON with `ok: true`
- dynamic targets return CORS `*`

---

## 5) Troubleshooting quick actions

- `404` on `/health`: deploy missing route or rewrite mismatch.
- `502`/timeout: app not listening on `$PORT`, crashloop, or domain not routed to live instance.
- HTML response on health path: frontend route caught request; add dedicated health endpoint/artifact.
- No CORS: add explicit headers to `OPTIONS` and `GET` handlers.
