# Wallet V1 Ecosystem Compatibility Audit
## Thronos Multi-Repo Integration Assessment

**Date:** 2026-05-22  
**Scope:** 13 accessible Thronos ecosystem repositories  
**Objective:** Identify wallet/address integration requirements and migration blockers before Wallet V1 deployment

---

## Executive Summary

### Risk Landscape
| Risk Level | Count | Repos |
|-----------|-------|-------|
| **HIGH** | 3 | gateway, roadway-assistant, commerce |
| **MEDIUM** | 6 | MEDICE, builder, virtual-commerce, verifyid, trader-sentinel, careerforge |
| **LOW** | 4 | btc-api-adapter, edupresence, skystriker, (driver-platform undefined) |

### Critical Findings
1. **Private keys stored in source config**: roadway-assistant (3 keys), MEDICE, careerforge
2. **Smart contract writes**: MEDICE (fever events), roadway-assistant (escrow/rewards)
3. **Payment orchestration**: gateway (multi-chain), builder (THR pricing), commerce (unknown scope)
4. **Address format inconsistency**: Mix of THR, EVM 0x, BTC addresses with no standardized validation
5. **No Wallet V1 signed envelope support**: All repos use legacy auth or no auth for blockchain operations

---

## Secret Exposure Index

The following table lists only the **variable name**, **file path**, and **required action**.
No actual secret values are recorded or reproduced anywhere in this document.

| Repo | Variable Name | File Path | Severity | Required Action |
|------|--------------|-----------|----------|-----------------|
| thronos-roadway-assistant | `THRONOS_DEPLOYER_PRIVATE_KEY` | `.env.example` | **CRITICAL** | Rotate immediately, move to vault |
| thronos-roadway-assistant | `THRONOS_PLATFORM_PRIVATE_KEY` | `.env.example` | **CRITICAL** | Rotate immediately, move to vault |
| thronos-roadway-assistant | `THRONOSCHAIN_PRIVATE_KEY` | `.env.example` | **CRITICAL** | Rotate immediately, move to vault |
| thronos-roadway-assistant | `THRONOS_ATTESTATION_API_KEY` | `.env.example` | HIGH | Rotate, replace with Wallet V1 signature verification |
| thronos-MEDICE | `MEDICE_PRIVATE_KEY` | `.env.example` | HIGH | Move to secure vault, implement key rotation |
| thronosbuilder | `TREASURY_AUTH_SECRET` | `.env.example` | MEDIUM | Replace with Wallet V1 signed refund envelopes |
| thronos-gateway | `GATEWAY_SECRET` | `.env.example` | MEDIUM | Replace with user signature verification |
| careerForgeThronos-AI | `ATTESTOR_PRIVKEY_HEX` | `.env.example` | MEDIUM | Move to vault, add nonce replay protection |

**Rule:** None of the above values appear in this document. If actual hex values or key material
are found in any repo's committed files (not .env.example), escalate as a security incident.

---

## Detailed Repository Analysis

### 1. thronos-btc-api-adapter
**Purpose:** Bitcoin blockchain data proxy  
**Status:** ✅ READY (No changes required)

| Field | Value |
|-------|-------|
| Language | Python (FastAPI) |
| Wallet Integration | None |
| Stores Secrets | No |
| Performs Writes | No |
| RPC Integration | External (Blockstream, Mempool.space) |
| Risk Level | **LOW** |

**Current Integration:**
- Read-only proxy to Bitcoin blockchain APIs
- No THR token interactions
- No private key management
- CORS restricted to Thronos domains

**Migration Impact:** None. Read-only operation requires no changes.

**Wallet V1 Dependency:** None.

---

### 2. thronos-gateway
**Purpose:** Payment & Service Orchestration Hub  
**Status:** 🔴 BLOCKERS IDENTIFIED

| Field | Value |
|-------|-------|
| Language | JavaScript/Node.js (Express) |
| Wallet Integration | **YES - CRITICAL** |
| Stores Secrets | walletAddress, payerAddress, txHash |
| Performs Writes | **YES** - Creates Payment records, processes fees |
| RPC Integration | Multi-chain (Thronos, ETH, BSC, Polygon, Arbitrum) |
| Risk Level | **HIGH** |

**Wallet Fields Used:**
```
Models: Payment (walletAddress, amountThrEquivalent, txHash)
         ThrPayWallet (wallet management)
         Service (treasury integration)

Treasury Address Variables:
- THR_TREASURY_ADDRESS (native)
- ETH_TREASURY_ADDRESS
- BSC_TREASURY_ADDRESS

Operations:
- Accepts user walletAddress as input
- Records txHash and payment state
- Splits fees: 50% Treasury, 25% Burn, 25% LP
- Stripe integration for fiat conversion
- Ether.fi card integration (Phase 1-2)
```

**Legacy Secret Stored:** `GATEWAY_SECRET` (symmetric, in `.env.example`)  
**Writes:** YES — creates Payment records, fee splits, treasury operations  
**Pledge/Whitelist Dependency:** Not currently checked — required before Wallet V1  
**References:** payment/commerce only; no NFT/pool/miner engines

**Critical Issues Before Wallet V1:**
1. `walletAddress` validation missing — accepts any string, no format check
2. Payment auth: `GATEWAY_SECRET` (symmetric) — not user-signed envelopes
3. No Wallet V1 signed envelopes for treasury operations
4. Cross-chain atomicity: no rollback mechanism
5. Hardcoded fee splits (50/25/25) — not aligned with Wallet V1 fee functions

**What Must Change (Future PRs):**
- [ ] Add address type detection (THR, 0x, BTC) with validation
- [ ] Implement Wallet V1 signed envelope support for payment submissions
- [ ] Replace `GATEWAY_SECRET` auth with user signature verification
- [ ] Update fee distribution to call Wallet V1 production fee functions
- [ ] Create payment atomic transaction log (idempotency)
- [ ] Add Wallet V1 activation check (`require_active_thr_address`) before payment
- [ ] Migrate `Payment.walletAddress` → `Payment.thr_address` (normalized)

**Wallet V1 Functions Required:**
- `require_active_thr_address()` — before payment acceptance
- `verify_signed_transaction_core()` — for payment authorization
- `calculate_fixed_burn_fee()` — for treasury fee distribution
- `split_and_credit_fee()` — for multi-party distribution

---

### 3. thronos-MEDICE
**Purpose:** Medical IoT Monitoring with Blockchain Anchoring  
**Status:** ⚠️ MEDIUM PRIORITY

| Field | Value |
|-------|-------|
| Language | Python |
| Wallet Integration | **PARTIAL** - Service wallet |
| Stores Secrets | **YES** - see Secret Exposure Index |
| Performs Writes | **YES** - Smart contract calls |
| RPC Integration | Thronos EVM + Fallback API |
| Risk Level | **MEDIUM** |

**Wallet Fields Used:**
- Service wallet address (signs on behalf of all IoT operations)
- `patient_ref` (SHA-256 hashed patient IDs — not a wallet address)
- `FEVER_CONTRACT_ADDRESS` (EVM smart contract target)

**Legacy Secrets:** `MEDICE_PRIVATE_KEY` — see Secret Exposure Index  
**Writes:** YES — `recordFeverEvent`, `closeFeverEvent`, hospital access control on-chain  
**Pledge/Whitelist Dependency:** Not currently used — patient consent model not implemented  
**References:** Medical IoT only; no NFT/pool/miner/commerce engines

**Smart Contract Operations:**
```
recordFeverEvent(patient_ref, temperature, timestamp)
closeFeverEvent(patient_ref)
getFeverHistory(patient_ref)   ← read
Hospital access control        ← write
```

**What Must Change (Future PRs):**
- [ ] Extract `MEDICE_PRIVATE_KEY` to secure vault
- [ ] Implement secp256k1 signing (currently EVM Web3 signing)
- [ ] Add nonce/timestamp verification for heartbeat replay protection
- [ ] Create separate service wallet vs patient consent wallet model
- [ ] Add event audit log (patient_ref, timestamp, operation, signature)

**Wallet V1 Functions Required:**
- `require_active_thr_address()` — optional patient consent gating
- `check_nonce_redis()` — heartbeat replay protection

---

### 4. thronos-edupresence
**Purpose:** Educational Attendance/Presence Tracking  
**Status:** ✅ READY (No changes required)

| Field | Value |
|-------|-------|
| Language | Python |
| Wallet Integration | None |
| Stores Secrets | None |
| Performs Writes | No wallet operations |
| RPC Integration | None (L2E integration disabled) |
| Risk Level | **LOW** |

**Current Integration:**
- QR code-based attendance; SMS/Viber notifications; JWT auth
- Optional L2E (learning-to-earn) integration currently disabled

**Migration Impact:** None required.  
**Wallet V1 Dependency:** Optional future only — L2E rewards via Wallet V1 signed transfers.

---

### 5. thronosbuilder
**Purpose:** Build-as-a-Service for Mobile Applications  
**Status:** ⚠️ MEDIUM PRIORITY

| Field | Value |
|-------|-------|
| Language | Dart (Flutter) + Node.js backend |
| Wallet Integration | **PARTIAL** - Payment treasury |
| Stores Secrets | **YES** - see Secret Exposure Index |
| Performs Writes | **YES** - Payment recording, refunds |
| RPC Integration | Thronos Node (payment verification) |
| Risk Level | **MEDIUM** |

**Wallet Fields Used:**
```
TREASURY_THR_ADDRESS       — THR payment recipient (hardcoded)
TREASURY_AUTH_SECRET       — authorization for refunds

Pricing (Native THR):
- Android APK: 10 THR
- iOS IPA: 50 THR
- Both: 45 THR

Exchange rate variables:
THR_USD_REFERENCE, ETH_USD_REFERENCE, BNB_USD_REFERENCE
```

**Legacy Secrets:** `TREASURY_AUTH_SECRET` — see Secret Exposure Index  
**Writes:** YES — payment records, refund authorization  
**Pledge/Whitelist Dependency:** Not currently checked  
**References:** Build payments only; no NFT/pool/miner/commerce engines

**What Must Change (Future PRs):**
- [ ] Replace `TREASURY_AUTH_SECRET` with Wallet V1 signed refund requests
- [ ] Validate user-provided wallet addresses (currently unchecked)
- [ ] Add `require_active_thr_address` pledge check for payment eligibility
- [ ] Create immutable payment ledger with chain anchor
- [ ] Add idempotency keys to prevent duplicate refunds

**Wallet V1 Functions Required:**
- `require_active_thr_address()` — payment eligibility
- `split_and_credit_fee()` — treasury fee distribution

---

### 6. thronos-roadway-assistant
**Purpose:** EV Battery Routing & Roadway Assistance  
**Status:** 🔴 CRITICAL - HIGHEST RISK

| Field | Value |
|-------|-------|
| Language | TypeScript/Next.js + Hardhat |
| Wallet Integration | **YES - CRITICAL** |
| Stores Secrets | **3 private keys + attestation key** — see Secret Exposure Index |
| Performs Writes | **YES** - Smart contracts (escrow, rewards, attestation) |
| RPC Integration | Thronos EVM (native chain) |
| Risk Level | **HIGH** |

**Wallet Fields Used:**
```
THRONOS_PLATFORM_WALLET        — service operation address
THRONOS_CHAIN_ID               — network identifier
THRONOS_EVM_RPC_URL            — native chain RPC
THRONOS_ATTESTATION_ENABLED    — true
THRONOS_ATTESTATION_MODE       — "sha256-node"
```

**Smart Contracts (On-chain state):**
```
THRONOS_ESCROW_CONTRACT        — service payment escrow
THRONOS_SERVICEBOOK_CONTRACT   — service registry
THRONOS_REWARD_VAULT_CONTRACT  — incentive distribution
THRONOS_REWARD_TOKEN_ADDRESS   — THR token
```

**Legacy Secrets:** 3 private keys + attestation API key — see Secret Exposure Index  
**Writes:** YES — escrow, service registry, reward vault, attestations  
**Pledge/Whitelist Dependency:** Not currently checked — required for service providers  
**References:** EV routing service economy; roadway infrastructure rewards

**Critical Issues:**
1. 3 private keys exposed in `.env.example` — rotate and move to vault before any production use
2. No key rotation mechanism — single static keys for all operations
3. Attestations not verified server-side
4. Hardcoded contract addresses — no upgrade path
5. No nonce/replay protection on attestations

**What Must Change (Future PRs):**
- [ ] **IMMEDIATE:** Move all private keys to secure vault (HashiCorp Vault, AWS KMS)
- [ ] Implement Wallet V1 signed envelopes for escrow operations
- [ ] Replace `THRONOS_ATTESTATION_API_KEY` with signature verification
- [ ] Add nonce/timestamp verification for attestation replay protection
- [ ] Implement `require_active_thr_address` for service providers
- [ ] Implement contract upgrade pattern (proxy contracts)
- [ ] Create attestation ledger with user signatures

**Wallet V1 Functions Required:**
- `verify_signed_transaction_core()` — attestation signature verification
- `require_active_thr_address()` — service provider admission
- `check_nonce_redis()` — attestation replay protection

**Timeline:** URGENT — resolve private key exposure before production deployment.

---

### 7. thronos-vitrual-comerce-assistant
**Purpose:** Virtual Commerce Assistant Service  
**Status:** ⚠️ CODE NOT FULLY EXPOSED

| Field | Value |
|-------|-------|
| Language | Python (backend directory present) |
| Wallet Integration | Unknown |
| Stores Secrets | Unknown |
| Performs Writes | Unknown |
| RPC Integration | Unknown |
| Risk Level | **MEDIUM** |

**Note:** Backend code not accessible via public API. Cannot complete assessment.

**What Must Change:** Cannot determine without code review of `backend/`.

**Recommendation:** Audit as part of thronos-commerce platform review.

---

### 8. thronos-commerce
**Purpose:** E-Commerce Platform  
**Status:** ⚠️ CODE SIZE BLOCKS FULL ANALYSIS

| Field | Value |
|-------|-------|
| Language | Node.js (EJS templating) |
| Wallet Integration | Likely **YES** |
| Stores Secrets | Unknown (`server.js` 318 KB) |
| Performs Writes | Likely YES — transactions, orders |
| RPC Integration | Likely YES |
| Risk Level | **MEDIUM** |

**Partial Findings:**
- `server.js` is 318 KB — exceeds single-pass analysis
- `lib/`, `utils/`, `views/` directories indicate payment/session handling
- Likely integrates with gateway payment flow
- Handles user accounts, shopping, checkout, payment processing

**Unanswered Questions (Require Code Review):**
1. Does it store user wallet addresses?
2. Does it verify THR payments on-chain?
3. Does it use legacy HMAC secrets?
4. Does it handle refunds/escrow?
5. Does it track order ownership by wallet address?

**What Must Change:** TBD — requires full `server.js` audit.

**Recommendation:** Prioritize deep audit; break monolith before migration.

---

### 9. thronos-verifyid
**Purpose:** Identity Verification & KYC Service  
**Status:** ⚠️ LOW PRIORITY

| Field | Value |
|-------|-------|
| Language | TypeScript (Frontend + Backend) |
| Wallet Integration | **MINIMAL** — auth context only |
| Stores Secrets | None (identity documents only) |
| Performs Writes | No blockchain writes |
| RPC Integration | None direct |
| Risk Level | **MEDIUM** |

**Current Integration:**
- KYC document verification; session-based auth
- Used by gateway and skystriker for user eligibility
- No wallet operations or blockchain integration

**Migration Impact:** None currently required.

**Potential Future Integration:** Bind verified identities to THR addresses for "verified wallet" status.

---

### 10. trader-sentinel
**Purpose:** Real-time Trading Sentiment & Market Monitoring  
**Status:** ⚠️ MINIMAL CODE EXPOSED

| Field | Value |
|-------|-------|
| Language | TypeScript (React Native) |
| Wallet Integration | Unknown |
| Stores Secrets | Unknown |
| Performs Writes | Unknown |
| RPC Integration | Unknown |
| Risk Level | **LOW-MEDIUM** |

**Current Integration:** Mobile app for trading analytics. No blockchain calls visible in exposed code.

**Recommendation:** Confirm read-only before clearing for migration pass-through.

---

### 11. driver-platform
**Status:** ❓ REPOSITORY NOT FOUND

| Field | Value |
|-------|-------|
| Status | Could not locate Thronos-specific repo |
| Risk Level | **UNKNOWN** |

**Recommendation:** Verify repo name and access scope.

---

### 12. skystriker
**Purpose:** Global Service Discovery & Guides  
**Status:** ✅ LOW PRIORITY

| Field | Value |
|-------|-------|
| Language | TypeScript/React (Frontend + Backend) |
| Wallet Integration | None |
| Stores Secrets | None |
| Performs Writes | Demo data seeding only |
| RPC Integration | None |
| Risk Level | **LOW** |

**Current Integration:** Service discovery, VerifyID integration, Google OAuth. No wallet operations.

**Migration Impact:** None required.

---

### 13. careerForgeThronos-AI
**Purpose:** AI-powered Career Guidance & Job Matching  
**Status:** ⚠️ MEDIUM PRIORITY

| Field | Value |
|-------|-------|
| Language | TypeScript/React + Python FastAPI |
| Wallet Integration | **PARTIAL** — attestation service |
| Stores Secrets | **YES** — see Secret Exposure Index |
| Performs Writes | **YES** — attestation submissions to chain |
| RPC Integration | Thronos Chain API |
| Risk Level | **MEDIUM** |

**Wallet Fields Used:**
```
ATTESTOR_PUBKEY_HEX         — public key for verification
SERVICE_PREFIX              — "THRONOS|AI_ATTESTATION|V1|careerforge|"
THRONOS_CHAIN_API_URL       — core node RPC
CHAIN_SUBMIT_PATH           — /tx/submit

Credit System (token economics):
COST_FULL_KIT=7 credits
COST_CV_ONLY=3, COST_INTERVIEW_PACK=3
```

**Legacy Secrets:** `ATTESTOR_PRIVKEY_HEX` — see Secret Exposure Index  
**Writes:** YES — attestation submissions, ServicePrefix registration  
**Pledge/Whitelist Dependency:** Not currently checked — required for premium features  
**References:** Career AI attestation only; no NFT/pool/miner/commerce engines

**Positive Note:** Already uses secp256k1 signing — architecturally closest to Wallet V1 compatibility.

**What Must Change (Future PRs):**
- [ ] Extract `ATTESTOR_PRIVKEY_HEX` to secure vault
- [ ] Add nonce/timestamp verification for attestation replay protection
- [ ] Tie credit purchases to Wallet V1 signed transfers
- [ ] Add `require_active_thr_address` for premium feature gating
- [ ] Support user-side self-attestation (user-signed envelope)

**Wallet V1 Functions Required:**
- `check_nonce_redis()` — replay protection
- `require_active_thr_address()` — premium access gating
- `split_and_credit_fee()` — credit purchase fee distribution

---

## Ecosystem Address Format Standardization

### Current State
```
THR Addresses:  "THR" + 40-hex — unvalidated in most repos
EVM Addresses:  0x<40-hex> — roadway-assistant, MEDICE
BTC Addresses:  P2PKH/P2SH/Bech32 — btc-api-adapter, builder

Problems:
- gateway accepts user walletAddress with no format check
- No cross-format detection (THR vs 0x vs BTC)
- Risk of payment routing to wrong chain
```

### Required: Address Type Detection
```python
def detect_address_type(address: str) -> str:
    """Return: 'thronos' | 'evm' | 'bitcoin' | 'invalid'"""
    if address.startswith('THR') and len(address) == 43:
        return 'thronos'
    if address.startswith('0x') and len(address) == 42:
        return 'evm'
    # bitcoin: P2PKH/P2SH/Bech32 detection
    return 'invalid'
```

Enforce in all payment models: gateway, builder, commerce.

---

## Phased Wallet V1 Migration Plan

### Phase 1: Read-Only Compatibility (Weeks 1-2)
**Goal:** All repos validate THR addresses and can check pledge/whitelist status.

**Actions:**
1. Create address validation service in thronos-v3.6 (shared across repos)
2. Export `require_active_thr_address()` as callable from external services
3. Add address validation to all input handlers (gateway, builder, commerce, MEDICE)
4. Add pledge status check before accepting THR addresses

**Repos Affected:** gateway, builder, commerce, MEDICE, careerforge  
**Risk:** LOW — read-only, no state changes

---

### Phase 2: Wallet V1 Signed Write Support (Weeks 3-6)
**Goal:** Accept Wallet V1 signed envelopes for write operations. Run dual-mode.

**Actions:**
1. Export `verify_signed_transaction_core()` for external service use
2. Implement signature verification in each writing repo
3. Replace symmetric secrets with signature verification (dual-mode first):
   - gateway: `GATEWAY_SECRET` → wallet signatures
   - builder: `TREASURY_AUTH_SECRET` → refund signatures
   - roadway-assistant: `ATTESTATION_API_KEY` → attestation signatures
4. Add nonce replay protection (Redis-based) in each writing repo
5. Create immutable transaction audit logs per repo

**Priority Order:** gateway → roadway-assistant → builder → commerce (post-audit)  
**Risk:** MEDIUM — dual-mode complexity, signature validation edge cases

---

### Phase 3: Legacy Address Migration Binding (Weeks 7-10)
**Goal:** Map old HMAC wallets (THR{timestamp}) to new secp256k1-derived addresses.

**Actions:**
1. Implement `migrate_legacy_to_wallet_v1()` endpoint in thronos-v3.6
2. Each repo updates stored wallet address bindings:
   - gateway: `Payment.walletAddress` → `legacy_address` + `new_v1_address`
   - builder: treasury address binding
   - commerce: user wallet bindings
3. Create explicit balance migration transaction (zero-fee, visible in `/api/transfers`)
4. Mark old addresses `legacy_migrated` (read-only after migration)

**Migration Flow:**
```
1. User provides: old_address + new_v1_address + HMAC proof of old ownership
2. Server verifies: pledge/whitelist active on old_address
3. Server verifies: HMAC(old_send_secret, nonce) is valid
4. Server creates: explicit balance migration transaction
5. Server marks: old_address as legacy_migrated
6. Server binds: old_address → new_v1_address
```

**Risk:** MEDIUM — address binding errors, users with multiple addresses

---

### Phase 4: Deprecate Legacy Secret Writes (Weeks 11-12)
**Goal:** All write operations require Wallet V1 signatures. Legacy auth removed.

**Actions:**
1. Remove dual-mode support from all repos
2. Update all tests to use Wallet V1 signatures only
3. Notify users 60+ days before cutoff
4. Monitor failed legacy auth attempts post-cutoff

**Repos:** gateway, builder, roadway-assistant, MEDICE, careerforge  
**Risk:** HIGH if Phase 2-3 incomplete — users lose access

---

## Risk Assessment Summary

### HIGH Risk — Immediate Action Required
| Repo | Issue | Immediate Action |
|------|-------|------------------|
| thronos-roadway-assistant | 3 private keys in config, smart contract writes | Rotate keys + move to vault (Week 1) |
| thronos-gateway | Live payment flows, no address validation | Phase 1 address check (Week 2) |
| thronos-commerce | 318 KB monolith, unknown wallet scope | Full code audit (Week 1-2) |

### MEDIUM Risk — Phase 2-3 Priority
| Repo | Issue |
|------|-------|
| thronos-MEDICE | Service wallet signing, smart contract writes |
| thronosbuilder | Treasury auth secret, refund flow |
| thronos-vitrual-comerce-assistant | Unknown scope (code not visible) |
| thronos-verifyid | Identity-wallet binding (future) |
| careerForgeThronos-AI | Attestation service, credit system |

### LOW Risk — No Immediate Action
| Repo | Reason |
|------|--------|
| btc-api-adapter | Read-only BTC proxy |
| thronos-edupresence | No wallet integration |
| skystriker | Service discovery only |
| trader-sentinel | Market monitoring (unconfirmed) |

---

## Smart Contract Inventory

| Repo | Variable Name | Purpose | Migration Required |
|------|--------------|---------|--------------------|
| thronos-MEDICE | `FEVER_CONTRACT_ADDRESS` | Fever event recording | Wallet V1 signature param |
| thronos-roadway-assistant | `THRONOS_ESCROW_CONTRACT` | Service payment escrow | Proxy upgrade + V1 signatures |
| thronos-roadway-assistant | `THRONOS_SERVICEBOOK_CONTRACT` | Service registry | Proxy upgrade + V1 signatures |
| thronos-roadway-assistant | `THRONOS_REWARD_VAULT_CONTRACT` | Reward distribution | Proxy upgrade + V1 signatures |
| careerForgeThronos-AI | Chain API (`/tx/submit`) | Attestation submission | Add nonce validation |

---

## Wallet V1 Function Dependencies Across Ecosystem

| Function | Required By |
|----------|------------|
| `require_active_thr_address()` | gateway, builder, roadway-assistant, MEDICE (optional), careerforge |
| `verify_signed_transaction_core()` | gateway, roadway-assistant |
| `calculate_fixed_burn_fee()` | gateway |
| `split_and_credit_fee()` | gateway, builder, careerforge |
| `check_nonce_redis()` | roadway-assistant, MEDICE, careerforge |
| `migrate_legacy_to_wallet_v1()` | gateway, builder, commerce |

---

## Implementation Timeline

### Week 1: Stabilization
- [ ] Rotate roadway-assistant private keys, move to vault (CRITICAL)
- [ ] Full code audit of thronos-commerce (priority)
- [ ] Create address validation service in thronos-v3.6

### Weeks 2-3: Phase 1 (Read-Only)
- [ ] gateway: Address validation + pledge check
- [ ] builder: Address validation + activation check
- [ ] MEDICE: Address validation for patient operations
- [ ] careerforge: Address validation in credit system

### Weeks 4-6: Phase 2 (Signed Writes)
- [ ] gateway: Signature verification, dual-mode support
- [ ] roadway-assistant: Contract updates, Wallet V1 attestation
- [ ] builder: Refund signature verification
- [ ] Redis nonce infrastructure (shared)

### Weeks 7-10: Phase 3 (Legacy Migration)
- [ ] `migrate_legacy_to_wallet_v1()` in thronos-v3.6
- [ ] Address binding updates in gateway, builder, commerce
- [ ] User migration toolkit

### Weeks 11-12: Phase 4 (Deprecation)
- [ ] Remove dual-mode
- [ ] Finalize tests
- [ ] 60-day user notification

---

## Repos Requiring No Wallet V1 Changes

- `btc-api-adapter` — read-only BTC proxy
- `thronos-edupresence` — no blockchain integration
- `skystriker` — service discovery only

---

## Conclusion

The ecosystem is migration-ready with the following critical gates:

1. **Rotate roadway-assistant private keys immediately** — security risk independent of Wallet V1
2. **Audit thronos-commerce server.js** — too large to assess without dedicated review
3. **Phased approach is mandatory** — 12 weeks, dual-mode in Phase 2 to avoid breakage
4. **Standardize address validation** — shared module across all payment repos
5. **Export Wallet V1 core functions** — `require_active_thr_address`, `verify_signed_transaction_core` must be callable from external services

**Timeline:** 12 weeks  
**Go-Live Gate:** Phase 1 (read-only) safe after Week 2; Phase 4 (exclusion) only after full Phase 2-3 completion

---

**Status:** Audit/Design Only — no code, API, contract, secret, or config changes made  
**Generated:** 2026-05-22  
**Allowed Changed File:** `ECOSYSTEM_WALLET_V1_COMPATIBILITY_AUDIT.md` only
