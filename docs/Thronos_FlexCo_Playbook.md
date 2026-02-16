# Thronos FlexCo 2026 — Operating Playbook

**Entity**: Thronos FlexCo e.U. (Austria)
**Version**: 2026.2
**Classification**: Internal / Investor-Ready
**Last Updated**: 2026-02-15

---

## Table of Contents

1. [A — Architecture & Service Inventory](#a--architecture--service-inventory)
2. [B — Security & Threat Model](#b--security--threat-model)
3. [C — Ops Runbook](#c--ops-runbook)
4. [D — Product Packaging (German-First)](#d--product-packaging-german-first)
5. [E — 2026 Roadmap & Grant Narrative](#e--2026-roadmap--grant-narrative)

---

## A — Architecture & Service Inventory

### A.1 Node Topology

| Node | Role | Platform | URL | Data Store |
|:-----|:-----|:---------|:----|:-----------|
| Node 1 (Master) | Chain Writer, API, Scheduler, AI Proxy | Railway | `thrchain.up.railway.app` | `ledger.sqlite3` (RW) |
| Node 2 (Replica) | Read-Only, BTC Watcher, Cross-Chain | Railway | `node-2.up.railway.app` | `ledger.sqlite3` (RO) |
| Node 3 (CDN) | Static Frontend, Wallet Widget | Vercel | `thronoschain.org` | None (static) |
| Node 4 (AI Core) | LLM Inference, Pytheia, Trading | Render | `thronos-v3-6.onrender.com` | `ai_sessions.db` |

### A.2 Subdomain → Repo → Data Store Map

| Subdomain | Repo | Data Store | Source-of-Truth |
|:----------|:-----|:-----------|:----------------|
| `thrchain.up.railway.app` | `Tsipchain/thronos-V3.6` | `ledger.sqlite3` | Node 1 (master writer) |
| `node-2.up.railway.app` | `Tsipchain/thronos-V3.6` | `ledger.sqlite3` (replicated) | Node 1 via sync |
| `thronoschain.org` | `Tsipchain/thronos-portal` | — | Git (Vercel auto-deploy) |
| `thronos-v3-6.onrender.com` | `Tsipchain/thronos-V3.6` | `ai_sessions.db` | Node 4 local |
| `btc-api.thronoschain.org` | `Tsipchain/thronos-V3.6` | Blockstream + local cache | External BTC RPCs |

### A.3 Data Ownership & Source-of-Truth

| Data Domain | Source-of-Truth | Replication | Notes |
|:------------|:----------------|:------------|:------|
| Blockchain ledger (blocks, TXs, balances) | Node 1 `ledger.sqlite3` | → Node 2 (read-only sync) | Node 1 is sole writer |
| AI sessions & chat history | Node 4 `ai_sessions.db` | None (local only) | Proxied via Node 1 |
| BTC bridge state | Node 1 `ledger.sqlite3` | Watcher on Node 2 writes via API to Node 1 | Node 2 detects, Node 1 writes |
| Music tracks / artist profiles | Node 1 `ledger.sqlite3` | — | Uploads stored on Node 1 filesystem |
| VerifyID device registry | Node 1 `ledger.sqlite3` | — | Challenge/response lifecycle |
| Frontend assets (HTML, JS, CSS) | Git → Vercel | Auto-deploy on push | CDN-cached globally |
| Custom tokens & EVM contracts | Node 1 `ledger.sqlite3` | — | On-chain via Node 1 |
| IoT telemetry & parking | Node 1 `ledger.sqlite3` | — | Device → API → DB |

### A.4 Replication Rules

1. **Master → Replica**: Node 2 syncs ledger from Node 1 via `bootstrap.json` heartbeat (every 30 s).
2. **Write prohibition**: `READ_ONLY=1` enforced on Node 2; any write attempt returns `403`.
3. **AI proxy**: Node 1 proxies `/api/ai/*` to Node 4 (`AI_CORE_URL`). If Node 4 is down, Node 1 falls back to local provider keys.
4. **Static deploy**: Vercel auto-deploys on `main` push. No runtime state.
5. **Cross-chain RPCs**: Only Node 1 holds full RPC keys (BTC, BSC, ETH, XRP, SOL). Node 2 holds BTC-watcher subset only.

### A.5 Offline / Online Node Topology

```
┌───────────────── ONLINE ZONE ──────────────────┐
│                                                  │
│  [Node 1 Master]──API proxy──▶[Node 4 AI Core]  │
│       │                                          │
│       │ heartbeat (30s)                          │
│       ▼                                          │
│  [Node 2 Replica]                                │
│                                                  │
│  [Node 3 Vercel CDN]  (static, no state)         │
│                                                  │
└──────────────────────────────────────────────────┘

┌───────────── OFFLINE / SURVIVAL ZONE ────────────┐
│                                                   │
│  [LoRa Antenna] ──15 km──▶ [IoT Miners]          │
│       │                                           │
│  [Peiko X9] ──Bluetooth──▶ [Audio-Fi / WAV TX]   │
│       │                                           │
│  [Solar Controller] ──RS485──▶ [G1 Mini / Ryzen]  │
│       │                                           │
│  [USB Block Erupters] ──USB──▶ [SHA256 PoW]      │
│                                                   │
│  Modes: Full | Eco | Survival (battery-aware)     │
│                                                   │
└───────────────────────────────────────────────────┘
```

---

## B — Security & Threat Model

### B.1 Wallet Security

| Threat | Control | Status |
|:-------|:--------|:-------|
| Seed phrase theft | BIP39/BIP44 HD derivation; mnemonic encrypted at rest (AES-256); Keychain/SecureEnclave on mobile | Active |
| Hot wallet compromise | Hot wallet holds minimal balance; BTC Pledge Vault is separate multisig | Active |
| Replay attacks | Nonce per TX; chain ID in signature | Active |
| Brute-force on Stratum port | Rate limiting + VerifyID attestation for miners | Active |

### B.2 VerifyID Threats

| Threat | Control |
|:-------|:--------|
| Challenge replay | 300 s TTL on HMAC challenges; single-use tokens |
| Device spoofing | SHA256 hardware attestation from USB Block Erupters |
| Admin bypass abuse | `ADMIN_SECRET` required; whitelist audit-logged |
| JWT forgery | HMAC-SHA256 signing with `JWT_SECRET`; rotation policy quarterly |

### B.3 Cross-Chain Event Bus & BTC Bridge

| Threat | Control |
|:-------|:--------|
| Phantom deposits | Watcher confirms ≥ 3 BTC confirmations via Blockstream + independent RPC |
| Double-spend on bridge | Lock-mint-burn pattern; minting only after finality |
| RPC endpoint poisoning | Fallback chain: Blockstream API → local BTC RPC → manual admin approval |
| Watcher downtime | Node 2 heartbeat monitored by Pytheia; alert after 3 consecutive failures |

### B.4 Peiko X9 Webhook / Audio Bridge

| Threat | Control |
|:-------|:--------|
| Bluetooth MITM | End-to-end encryption on payload; AES-256 pre-shared key |
| Audio injection | CRC-32 checksum embedded in WAV; rejected on mismatch |
| Jamming / DoS | SDR spectrum monitor (RTL-SDR v4) detects anomalous RF; auto-failover to LoRa |

### B.5 Admin Console

| Threat | Control |
|:-------|:--------|
| Unauthorized access | `ADMIN_SECRET` header + IP allowlist (configurable) |
| Privilege escalation | Role-based JWT (admin/operator/viewer); least privilege |
| Audit gap | All admin actions logged to `admin_audit_log` table with timestamp, actor, action |

### B.6 Secrets Hygiene

| Secret | Storage | Rotation |
|:-------|:--------|:---------|
| `ADMIN_SECRET` | Railway/Render env vars | Quarterly |
| `JWT_SECRET` | Railway/Render env vars | Quarterly |
| OpenAI / Anthropic / Google API keys | Railway env vars (Node 1 only) | On compromise |
| BTC/BSC/ETH RPC URLs | Railway env vars (Node 1 only) | Static (provider-managed) |
| Stripe secret key | Railway env vars | Annually |
| `CHAIN_PRIVATE_KEY` | Railway env vars | On compromise |

**Rules**:
- Never commit secrets to Git (`.env` in `.gitignore`).
- No secrets on Node 3 (static CDN).
- Node 2 holds only `ADMIN_SECRET` + BTC watcher subset.

### B.7 Key Custody (Multisig / Quorum)

- **Treasury Wallet**: 2-of-3 multisig (founder + CTO + Pytheia AI signer).
- **BTC Pledge Vault**: Separate cold wallet; manual release only.
- **Quorum Consensus**: BFT with BLS signatures; ≥ 2/3 validator votes to finalize block.
- **Emergency**: Founder holds offline recovery seed in bank safe deposit (Austria).

### B.8 Audit Logging

All critical events written to `admin_audit_log`:
- Wallet creation / large transfers (> 1000 THR)
- Bridge mint / burn operations
- VerifyID registrations
- Admin whitelist changes
- AI model switches
- Pytheia autonomous actions

Retention: 365 days minimum. Export: JSON via `/api/admin/audit-export`.

---

## C — Ops Runbook

### C.1 DNS / CNAME Rules

| Domain | Type | Target | Provider |
|:-------|:-----|:-------|:---------|
| `thronoschain.org` | A (Apex) | Vercel IP | Vercel |
| `www.thronoschain.org` | CNAME | `cname.vercel-dns.com` | Vercel |
| `btc-api.thronoschain.org` | CNAME | Railway custom domain | Railway |
| `thrchain.up.railway.app` | Platform | Railway auto | Railway |
| `thronos-v3-6.onrender.com` | Platform | Render auto | Render |

**Adding a new custom domain**:
1. Add CNAME record at DNS provider → platform target.
2. Platform: Railway → `Settings > Custom Domains > Add`; Render → `Settings > Custom Domains`.
3. Vercel: `vercel domains add <domain>` via CLI.
4. Wait for SSL provisioning (Let's Encrypt, usually < 5 min).
5. Update `thronos_registry.yaml` → `domains` section.
6. Run `python scripts/generate_bootstrap.py` to regenerate portal config.

### C.2 Environment Variables Checklist

**Node 1 (Master) — Required**:
```
NODE_ROLE=master
NODE_NAME=node1-master
THRONOS_ENV=production
READ_ONLY=0
IS_LEADER=1
SCHEDULER_ENABLED=1
ENABLE_CHAIN=1
DOMAIN_URL=https://thrchain.up.railway.app
API_BASE_URL=https://thrchain.up.railway.app
LEADER_URL=https://thrchain.up.railway.app
REPLICA_EXTERNAL_URL=https://node-2.up.railway.app
THRONOS_AI_MODE=proxy
AI_CORE_URL=https://thronos-v3-6.onrender.com
ADMIN_SECRET=<secret>
JWT_SECRET=<secret>
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
BTC_RPC_URL=...
BSC_RPC_URL=https://bsc-dataseed.binance.org
ETH_RPC_URL=...
XRP_RPC_URL=https://s1.ripple.com:51234
SOL_RPC_URL=https://api.mainnet-beta.solana.com
STRIPE_SECRET_KEY=sk_live_...
```

**Node 2 (Replica) — Required**:
```
NODE_ROLE=replica
READ_ONLY=1
SCHEDULER_ENABLED=0
ADMIN_SECRET=<same-secret>
LEADER_URL=https://thrchain.up.railway.app
BTC_RPC_URL=...
```

**Node 4 (AI Core) — Required**:
```
NODE_ROLE=ai-core
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
ADMIN_SECRET=<same-secret>
```

### C.3 Backup & Restore

**Daily automated backup** (via scheduler on Node 1):
```bash
# Backup ledger
sqlite3 /app/data/ledger.sqlite3 ".backup '/app/backups/ledger_$(date +%Y%m%d).sqlite3'"

# Backup AI sessions (Node 4)
sqlite3 /app/data/ai_sessions.db ".backup '/app/backups/ai_sessions_$(date +%Y%m%d).db'"
```

**Restore procedure**:
1. Stop scheduler: set `SCHEDULER_ENABLED=0` on Node 1, redeploy.
2. Copy backup file to `/app/data/ledger.sqlite3`.
3. Re-enable scheduler, redeploy.
4. Verify via `/api/block/latest` — block height should match pre-backup.

**Off-site**: Weekly export to encrypted archive (GPG) on founder's secure storage.

### C.4 Incident Playbook

#### Severity Levels

| Level | Definition | Response Time | Escalation |
|:------|:-----------|:--------------|:-----------|
| SEV-1 | Chain halted, bridge compromised, data loss | 15 min | Founder + CTO immediately |
| SEV-2 | Service degraded (Node down, slow API) | 1 hour | On-call engineer |
| SEV-3 | Minor issue (UI bug, non-critical endpoint) | 24 hours | Next business day |

#### Common Incidents

**Node 1 (Master) Down**:
1. Check Railway dashboard → deployment logs.
2. If OOM: increase memory in Railway settings.
3. If crash loop: check `start.sh` and recent commits.
4. If Railway outage: activate read-mode on Node 2 with `IS_LEADER=1` (emergency failover).
5. Post-mortem within 48 hours.

**BTC Bridge Watcher Stalled**:
1. Check Node 2 logs for `btc_pledge_watcher` errors.
2. Verify BTC RPC endpoint is reachable.
3. Fallback: manually verify via Blockstream.info and admin-approve pledges.

**Render (AI Core) Cold Start**:
1. Render free tier spins down after inactivity.
2. Node 1 auto-falls-back to local AI provider keys.
3. Ping `https://thronos-v3-6.onrender.com/api/health` to wake.
4. Consider upgrading to Render paid plan for zero-downtime.

**Vercel Deploy Failure**:
1. Check Vercel dashboard → build logs.
2. Static site — no runtime risk; previous deploy stays live.
3. Fix build error in repo; push again.

### C.5 Release Discipline

1. **Branch model**: `main` (production), feature branches (`feature/*`), hotfix branches (`hotfix/*`).
2. **PR required**: All changes via Pull Request; minimum 1 review (founder or CTO).
3. **CI checks**: Lint + basic tests must pass before merge.
4. **Deploy**: Railway and Render auto-deploy on merge to `main`. Vercel auto-deploys portal repo.
5. **Rollback**: Railway → "Rollback to previous deployment" button. Render → same. Vercel → `vercel rollback`.
6. **Changelog**: Update `CHANGELOG.md` with version, date, changes.
7. **Registry update**: After adding/removing any service, update `thronos_registry.yaml` and regenerate `bootstrap.json`.

---

## D — Product Packaging (German-First)

### D.1 Three Commercial Bundles

#### Bundle 1: VerifyID Enterprise

**Target**: Logistics, fleet management, KYC-light compliance.

| Feature | Description |
|:--------|:-----------|
| Device registration | Hardware attestation via SHA256 ASIC proof |
| Challenge/response auth | Cryptographic device identity, 5-min TTL |
| API integration | RESTful API for enterprise identity workflows |
| Audit trail | Immutable on-chain log of all verifications |
| Multi-language UI | DE, EN, EL, ES, FR, JA, ZH |

**Pricing Skeleton**:
- Starter: €99/mo — up to 100 devices, 10k verifications/mo
- Business: €499/mo — up to 1,000 devices, 100k verifications/mo
- Enterprise: Custom — unlimited, SLA, dedicated support

**Pilot KPIs**: 3 paying customers in AT/DACH within 6 months; < 200 ms avg verification time; 99.5% uptime.

#### Bundle 2: Driver Telemetry & T2E (Train-to-Earn)

**Target**: Fleet operators, autonomous driving R&D, insurance telematics.

| Feature | Description |
|:--------|:-----------|
| GPS telemetry ingestion | Real-time route data with on-device hashing |
| Privacy-by-design | No raw GPS stored; proof-of-route only |
| T2E rewards | THR token rewards for quality driving data |
| AI training pipeline | Aggregated telemetry feeds autonomous driving models |
| Driver dashboard | Real-time stats, earnings, route quality score |

**Pricing Skeleton**:
- Pilot: €199/mo — up to 50 vehicles
- Fleet: €799/mo — up to 500 vehicles, priority data pipeline
- Enterprise: Custom — white-label, on-prem option

**Pilot KPIs**: 1 fleet operator (20+ vehicles) in AT within 6 months; 10,000 km of telemetry data; measurable model improvement.

#### Bundle 3: IoT Telemetry + AI L2 Intelligence

**Target**: Smart city, parking, environmental monitoring, industrial IoT.

| Feature | Description |
|:--------|:-----------|
| IoT device onboarding | VerifyID-based device registration |
| Sensor data pipeline | LoRa / WiFi / Bluetooth telemetry ingestion |
| AI L2 processing | On-chain AI inference for anomaly detection |
| Smart parking | Real-time parking availability + THR payments |
| Mining rewards | IoT devices earn THR via T2E data contributions |
| Off-grid capability | LoRa + solar for infrastructure-independent operation |

**Pricing Skeleton**:
- City Pilot: €299/mo — up to 200 IoT nodes, basic AI
- City Pro: €999/mo — up to 2,000 nodes, full AI L2
- National: Custom — unlimited, government SLA

**Pilot KPIs**: 1 smart parking pilot (50+ sensors) in Vienna/Graz; sub-second occupancy detection; positive ROI within 12 months.

### D.2 Compliance Notes (AML/KYC Boundaries)

- **Thronos is NOT a bank or payment institution**. THR is a utility token within the ecosystem.
- **VerifyID is NOT a KYC provider** in the regulated sense. It provides device identity and hardware attestation. Human identity verification is delegated to certified partners if required.
- **AML boundary**: Fiat on-ramp (Stripe) handles AML/KYC. Thronos does not custody fiat.
- **BTC Bridge**: Pledge system requires user to self-declare; Thronos does not hold or transmit BTC on behalf of users (non-custodial).
- **GDPR**: No raw personal data stored on-chain. GPS data hashed on-device. Right-to-erasure applies to off-chain databases only.
- **Austrian regulatory**: FlexCo e.U. registered in Austria. Token utility classification under MiCA framework (utility token, not e-money).

---

## E — 2026 Roadmap & Grant Narrative

### E.1 Milestones (Q2–Q4 2026)

#### Q2 2026 (April–June)
- [ ] Complete LoRa antenna integration (15 km off-grid mesh)
- [ ] Solar energy controller (Victron/RS485) production-ready
- [ ] Android APK signed release + Play Store submission
- [ ] VerifyID Enterprise Bundle — beta launch with 1 DACH customer
- [ ] Automated BTC ↔ WBTC bridge (multisig)
- [ ] Driver Telemetry pilot — 1 fleet operator onboarded

#### Q3 2026 (July–September)
- [ ] iOS native wallet (App Store submission)
- [ ] AI Model Marketplace — on-chain model trading with THR
- [ ] Lightning Network integration for micropayments
- [ ] IoT Smart City pilot — Vienna/Graz parking
- [ ] SDR spectrum monitor (RTL-SDR v4) field-tested
- [ ] Peiko X9 audio bridge production-ready

#### Q4 2026 (October–December)
- [ ] API Credits System — pay for AI calls with THR
- [ ] On-chain model attestations
- [ ] Decentralized inference network (multi-node)
- [ ] AI Safety & Governance DAO launch
- [ ] 3 paying enterprise customers (VerifyID + Telemetry)
- [ ] FFG grant milestone report

### E.2 Grant-Fit Narrative (AWS / FFG)

**Thronos is an Austrian-built, privacy-first blockchain OS** that creates value at the intersection of AI, IoT, and decentralized identity — three pillars of Austria's digital transformation strategy.

**Why Austria**: Thronos FlexCo is registered in Austria, employs Austrian talent, and targets DACH-first use cases (fleet management, smart city, industrial IoT). Revenue stays in Austria.

**Innovation**: Thronos is unique in combining SHA256 blockchain with off-grid survival protocols (audio, radio, solar), AI-powered autonomous agents (Pytheia), and Train-to-Earn data economics — capabilities not found in any single platform today.

**FFG alignment**: Fits "IKT der Zukunft" and "Produktion der Zukunft" — enabling Austrian SMEs to leverage blockchain + AI without building infrastructure from scratch.

**AWS Credits alignment**: Cloud-native deployment on Railway/Render today; AWS migration path for enterprise-grade SLA. Credits accelerate time-to-market for 3 commercial bundles.

### E.3 One-Page: "Austrian Value Creation" Story

---

**THRONOS — Blockchain-OS aus Österreich**

Thronos ist ein in Österreich entwickeltes Blockchain-Betriebssystem, das KI, IoT und dezentrale Identität vereint — alles "Made in Austria".

**Was wir bauen**: Eine Plattform, die es Unternehmen ermöglicht, Geräte zu verifizieren (VerifyID), Telemetriedaten sicher zu sammeln (Driver/IoT Telemetry) und KI-Modelle dezentral zu trainieren — alles auf einer eigenen SHA256-Blockchain mit dem Utility-Token THR.

**Wertschöpfung in Österreich**:
- FlexCo e.U. in Österreich registriert
- Erste Kunden und Pilotprojekte in DACH
- Arbeitsplätze in Entwicklung, DevOps und Vertrieb
- Steuereinnahmen und IP verbleiben in Österreich

**Marktchance**: Der globale IoT-Markt wächst auf €1,5 Billionen bis 2030. Österreich kann mit Thronos eine Nische in "vertrauenswürdiger IoT-Identität" besetzen — privacy-by-design, off-grid-fähig, KI-gestützt.

**Nächste Schritte**: 3 kommerzielle Bundles (VerifyID, Driver Telemetry, IoT+AI) mit ersten zahlenden Kunden bis Q4 2026. FFG-Förderung beschleunigt die Markteinführung um 6 Monate.

*"Pledge to the unburnable — Stärke in jedem Block."*

---
