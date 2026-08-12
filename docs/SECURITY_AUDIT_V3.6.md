# ThronosChain V3.6 — Security Audit Report

**Date**: 2026-08-12
**Scope**: `Tsipchain/thronos-V3.6` repository, `main` branch
**Auditor**: Automated (Phase 2 hardening pass)
**Status**: DRAFT — DO NOT DEPLOY, DO NOT MERGE TO PRODUCTION

---

## CRITICAL: `.env` tracked by Git

**Finding**: `.env` is checked into git history despite `.gitignore` listing it.
The file was added in commit `7532eac` (merge of PR #664).

**Impact**: All secrets in `.env` are exposed in the repository's full git history.
Even after removing the file from tracking, the secrets remain in historical commits.

**Remediation applied this PR**:
- `git rm --cached .env` — file is no longer tracked (still on disk)
- `.gitignore` already excludes `.env` — future `git add .` will not re-add it

**Remediation required (MANUAL, by repo owner)**:
- **Rotate ALL credentials** listed in the Secret Rotation Checklist below
- Consider `git filter-branch` or BFG Repo Cleaner to purge `.env` from history
  (destructive — do NOT run automatically; requires team coordination)

## CRITICAL: `miner_kit/vehicle_key.json` tracked by Git

**Finding**: Contains `vehicle_id`, `private_key`, and `public_key` fields.
Private key material is committed to the repository.

**Remediation applied this PR**:
- `git rm --cached miner_kit/vehicle_key.json`
- Added `**/vehicle_key.json` and `**/private_key*.json` to `.gitignore`

**Remediation required (MANUAL)**: Rotate any vehicle keys derived from the committed values.

---

## `.env` Variable Names (values NOT displayed)

### LLM / AI Provider Keys (ROTATE)
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `AI_CORE_URL`
- `AI_CORE_MODEL`
- `AI_LOG_API_KEY`
- `APP_AI_KEY`

### Admin & Internal Auth (ROTATE)
- `ADMIN_SECRET`
- `APP_SECRET_KEY`
- `X9_VOICE_WEBHOOK_SECRET`

### Payment / Stripe (ROTATE)
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`

### Database & Cache (ROTATE if contains credentials)
- `DATABASE_URL`
- `REDIS_URL`

### Blockchain / Wallet (REVIEW — public addresses are not secrets)
- `BTC_PLEDGE_VAULT` (public address — low risk)
- `BTC_HOT_WALLET` (public address — low risk)
- `BTC_TREASURY` (public address — low risk)
- `ARBITRUM_RPC_URL`, `BSC_RPC_URL`, `ETH_RPC_URL`, `POLYGON_RPC_URL`, `OPTIMISM_RPC_URL`, `SOLANA_RPC_URL`, `XRP_RPC_URL` (public endpoints — low risk)

### Application Config (no rotation needed)
- `APP_ENV`, `APP_VERSION`, `NODE_ROLE`, `IS_LEADER`, `READ_ONLY`
- `SCHEDULER_ENABLED`, `HEARTBEAT_ENABLED`, `HEARTBEAT_LOG_ERRORS`
- `DATA_DIR`, `MUSIC_VOLUME`, `DOMAIN_URL`
- `PUBLIC_URL`, `MASTER_URL`, `MASTER_PUBLIC_URL`
- `BOOTSTRAP_*` (service discovery URLs — public)
- `BTC_NETWORK_FEE`, `MIN_BTC_WITHDRAWAL`, `MAX_BTC_WITHDRAWAL`
- `WITHDRAWAL_FEE_PERCENT`, `THR_BTC_RATE`
- `MINING_*` (rate-limit config)
- `ENABLE_MICRO_MINER`, `STRATUM_PORT`
- `THRONOS_AI_MODE`, `REDIS_CACHE_ENABLED`
- `GUEST_*`, `AI_FREE_MESSAGES_LIMIT`
- `MUSIC_MODAL_ENABLED`, `PYTHEIA_STANDALONE`
- `THR_OFFLINE_CORPUS_ENABLED`, `THR_THAI_ENABLED`
- `USE_SQLITE_LEDGER`, `ASSET_CDN_BASE`

---

## Secret Rotation Checklist

| # | Secret | Priority | Action |
|---|--------|----------|--------|
| 1 | `ANTHROPIC_API_KEY` | **CRITICAL** | Regenerate in Anthropic console, update Railway |
| 2 | `OPENAI_API_KEY` | **CRITICAL** | Regenerate in OpenAI dashboard, update Railway |
| 3 | `GEMINI_API_KEY` | **CRITICAL** | Regenerate in Google AI Studio, update Railway |
| 4 | `ADMIN_SECRET` | **CRITICAL** | Generate new `secrets.token_urlsafe(48)`, update Railway |
| 5 | `APP_SECRET_KEY` | **CRITICAL** | Generate new `secrets.token_urlsafe(48)`, update Railway |
| 6 | `APP_AI_KEY` | **CRITICAL** | Generate new `secrets.token_urlsafe(48)`, update Railway |
| 7 | `AI_LOG_API_KEY` | HIGH | Generate new value, update Railway |
| 8 | `X9_VOICE_WEBHOOK_SECRET` | HIGH | Regenerate in voice provider, update Railway |
| 9 | `STRIPE_SECRET_KEY` | **CRITICAL** | Roll key in Stripe Dashboard, update Railway |
| 10 | `STRIPE_PUBLISHABLE_KEY` | HIGH | Roll key in Stripe Dashboard, update Railway |
| 11 | `STRIPE_WEBHOOK_SECRET` | **CRITICAL** | Regenerate webhook signing secret in Stripe, update Railway |
| 12 | `DATABASE_URL` | HIGH | Change password if URL contains credentials |
| 13 | `REDIS_URL` | HIGH | Change password if URL contains credentials |
| 14 | `vehicle_key.json` private_key | HIGH | Regenerate vehicle keypair |

---

## Additional Security Findings

### 1. `ADMIN_SECRET` defaults to `"CHANGE_ME_NOW"` (server.py:910)
```python
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")
```
Warning is logged but server continues running. This is a known-insecure default.
**Recommendation**: Fail-closed on production (`APP_ENV=production`).

### 2. `AI_LOG_API_KEY` falls back to `ADMIN_SECRET` (server.py:795)
```python
AI_LOG_API_KEY = os.getenv("AI_LOG_API_KEY", os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW"))
```
If `AI_LOG_API_KEY` is unset, it reuses `ADMIN_SECRET`. Two separate secrets should not share values.

### 3. `_check_aicore_key()` bypasses auth when `APP_AI_KEY` is empty (server.py:46772-46774)
```python
def _check_aicore_key() -> bool:
    if not _APP_AI_KEY:
        return True  # ← no auth at all
```
If `APP_AI_KEY` is not set, all AI-core endpoints are open. In production, this should fail closed.

### 4. Master/Replica Guards
The codebase has solid master/replica separation:
- `READ_ONLY` enforced on replica nodes
- `_enforce_write_protection()` wraps `save_json` and `atomic_write_json`
- Scheduler, voting init, AI pool operations gated on `is_master()`
- Chain file list is explicit in `_is_chain_file()`

**This is good architecture for Phase 3**: the `contract_proof` module should use the same `is_master()` / `_enforce_write_protection()` pattern.

### 5. Transaction ID Generation
`tx_id` is generated as `hashlib.sha256(payload).hexdigest()[:16]` — deterministic, which supports idempotency for duplicate detection. Phase 3 should follow this pattern for `CONTRACT_ANCHOR_V1` transactions.

### 6. Internal Service Auth Pattern
Services authenticate via `X-API-Key`, `X-Internal-Key`, or `X-Admin-Secret` headers, checked against env-configured secrets. Phase 3 contract proof endpoints should follow this existing pattern using a dedicated `THRONOS_CONTRACT_PROOF_API_KEY`.

---

## HARD STOP

- Do NOT rotate credentials automatically
- Do NOT rewrite git history automatically
- Do NOT deploy to Railway
- Do NOT modify production data
- All remediations above are for the repo owner to execute manually after review
